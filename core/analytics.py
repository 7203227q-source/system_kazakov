import datetime
from django.utils import timezone
from django.db.models import Avg, F, Count
from .models import TaskLog, DailySnapshot, StudentSubjectProfile, Submission, Assignment

ALPHA = 0.25  # Коэффициент экспоненциального сглаживания (EMA)

def calculate_time_anomaly(task, time_spent, is_verified):
    """
    Определяет, является ли время решения аномальным.
    Если задача решается в Verified Mode, мы сохраняем время для бенчмарка.
    """
    # Для MVP: Если задача решена быстрее 5 секунд, это подозрительно
    if time_spent < 5 and not is_verified:
        return True
        
    # Продвинутая логика (Вариант Б из спецификации): 
    # Сравниваем с медианным временем по этому типу задач в Verified сессиях
    verified_logs = TaskLog.objects.filter(
        task__task_type=task.task_type, 
        is_verified=True
    ).exclude(time_spent=0)
    
    if verified_logs.exists():
        # Упрощенная медиана: среднее значение
        avg_verified_time = verified_logs.aggregate(Avg('time_spent'))['time_spent__avg']
        if avg_verified_time and time_spent < (0.4 * avg_verified_time):
            return True

    return False

def record_task_log(student, task, submission, assignment, time_spent):
    """
    Создает детальный лог решения задачи (TaskLog).
    Вызывается при сохранении ответа ученика.
    """
    is_verified = False
    verifier_role = None
    
    if assignment and assignment.is_verified:
        is_verified = True
        verifier_role = 'tutor'
        
    # Рассчитываем балл (нормализуем к 0-100 для внутреннего мастерства или оставляем как есть)
    score = 0.0
    if submission and submission.is_correct:
        score = float(task.exam_points)
    elif submission and submission.primary_score:
        score = float(submission.primary_score)
        
    is_anomaly = calculate_time_anomaly(task, time_spent, is_verified)
    
    log = TaskLog.objects.create(
        student=student,
        task=task,
        submission=submission,
        assignment=assignment,
        time_spent=time_spent,
        score=score,
        is_verified=is_verified,
        verifier_role=verifier_role,
        is_anomaly=is_anomaly
    )
    
    # После записи лога обновляем профиль
    update_student_analytics(student, task.topic.subject)
    return log

def update_student_analytics(student, subject):
    """
    Обновляет показатели мастерства и прогнозы в профиле ученика и DailySnapshot.
    """
    profile, _ = StudentSubjectProfile.objects.get_or_create(
        student=student, 
        subject=subject
    )
    
    # 1. Расчет EMA Mastery (только по не-аномальным логам)
    recent_logs = TaskLog.objects.filter(
        student=student, 
        task__topic__subject=subject,
        is_anomaly=False
    ).order_by('created_at')
    
    current_mastery = 0.0
    
    for log in recent_logs:
        # Нормализуем score задачи к 100-балльной шкале (условно, 1 балл = 100% успеха для задачи в 1 балл)
        # Если задача стоит 2 балла, и ученик получил 1, то это 50%
        max_points = float(log.task.exam_points)
        task_success_rate = (log.score / max_points * 100) if max_points > 0 else 0.0
        
        # Если это верифицированная сессия, даем ей больший вес (Trust Score = 1.0 vs 0.6)
        weight = 1.0 if log.is_verified else profile.trust_factor
        
        effective_score = task_success_rate * weight
        
        if current_mastery == 0.0:
            current_mastery = effective_score
        else:
            current_mastery = (effective_score * ALPHA) + (current_mastery * (1 - ALPHA))
            
    # 2. Обновление Daily Snapshot
    today = timezone.now().date()
    snapshot, created = DailySnapshot.objects.get_or_create(
        student=student,
        subject=subject,
        date=today
    )
    
    # 3. Расчет прогноза (Простая линейная экстраполяция для MVP)
    # Predicted Score = Current Mastery * Learning Velocity
    predicted_score = current_mastery * profile.learning_velocity
    
    # Ограничиваем прогноз
    predicted_score = max(0.0, min(100.0, predicted_score))
    
    snapshot.current_mastery = round(current_mastery, 2)
    snapshot.predicted_exam_score = round(predicted_score, 2)
    
    # 4. Анализ разрыва (Gap Analysis)
    solo_avg = TaskLog.objects.filter(student=student, is_verified=False).aggregate(Avg('score'))['score__avg'] or 0
    verified_avg = TaskLog.objects.filter(student=student, is_verified=True).aggregate(Avg('score'))['score__avg'] or 0
    
    if verified_avg > 0 and solo_avg > 0:
        # Если в соло он решает на 100%, а при репетиторе на 50%, разрыв огромный
        gap = solo_avg - verified_avg
        snapshot.gap_between_solo_and_verified = round(gap, 2)
        
        # Корректируем Trust Factor
        if gap > (0.3 * task.exam_points): # Если разрыв больше 30%
            profile.trust_factor = max(0.1, profile.trust_factor - 0.05)
        elif gap < (0.1 * task.exam_points):
            profile.trust_factor = min(1.0, profile.trust_factor + 0.05)
            
    snapshot.save()
    profile.save(update_fields=['trust_factor'])
    
    return snapshot