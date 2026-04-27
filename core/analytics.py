import datetime
from django.utils import timezone
from django.db.models import Avg, F, Count, Max, Q
from .models import TaskLog, DailySnapshot, StudentSubjectProfile, Submission, Assignment, Task, Topic
import random

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

def get_adaptive_task_for_student(student):
    """
    Алгоритм интервального повторения (Адаптивный Тренажер).
    Детализированный уровень: Topic + task_type + конкретные затыки.
    """
    active_subjects = student.subject_profiles.values_list('subject_id', flat=True)
    
    if not active_subjects:
        return Task.objects.order_by('?').first()
        
    # 1. Группируем по уникальным парам (topic_id, task_type)
    # Используем модель Task как базовую для агрегации
    subtopics = Task.objects.filter(topic__subject_id__in=active_subjects).values('topic_id', 'task_type').annotate(
        last_practiced=Max('task_logs__created_at', filter=Q(task_logs__student=student)),
        total_attempts=Count('task_logs', filter=Q(task_logs__student=student)),
        correct_attempts=Count('task_logs', filter=Q(task_logs__student=student, task_logs__score__gt=0))
    )
    
    now = timezone.now()
    subtopic_priorities = []
    
    for st in subtopics:
        priority = 0.0
        
        if st['total_attempts'] == 0:
            # Новый подтип - высокий приоритет
            priority = 2.0
        else:
            # 2. Фактор забывания
            days_since = (now - st['last_practiced']).days if st['last_practiced'] else 0
            forgetting_factor = min(1.5, days_since * 0.1)
            
            # 3. Фактор ошибок
            accuracy = st['correct_attempts'] / st['total_attempts']
            error_factor = 1.0 - accuracy 
            
            priority = forgetting_factor + (error_factor * 1.5)
            
        subtopic_priorities.append({
            'topic_id': st['topic_id'],
            'task_type': st['task_type'],
            'priority': priority
        })
        
    if not subtopic_priorities:
        return Task.objects.order_by('?').first()
        
    # Сортируем подтипы по приоритету
    subtopic_priorities.sort(key=lambda x: x['priority'], reverse=True)
    
    # Берем Топ-3 самых "больных" подтипов
    top_subtopics = subtopic_priorities[:3]
    selected_subtopic = random.choice(top_subtopics)
    
    # 4. Выбор задачи внутри подтипа (Spaced Repetition для конкретной задачи)
    base_query = Task.objects.filter(
        topic_id=selected_subtopic['topic_id'], 
        task_type=selected_subtopic['task_type']
    )
    
    # Шаг А: Есть ли в этом подтипе задача, в которой ученик ошибался, 
    # и которую он давно не повторял? (Конкретный "затык")
    failed_tasks = base_query.filter(
        task_logs__student=student,
        task_logs__score=0 # Была ошибка
    ).annotate(
        last_failed=Max('task_logs__created_at')
    ).order_by('last_failed')
    
    # Если есть старая ошибка, подкидываем её снова (Spaced Repetition)
    if failed_tasks.exists():
        # Берем ту, где ошибался дольше всего назад
        return failed_tasks.first()
    
    # Шаг Б: Ищем задачу, которую вообще не решали
    unsolved_tasks = base_query.exclude(task_logs__student=student)
    if unsolved_tasks.exists():
        return unsolved_tasks.order_by('?').first()
        
    # Шаг В: Если всё решено и ошибок нет, берем самую старую решенную для повторения
    oldest_solved = base_query.filter(task_logs__student=student).annotate(
        last_log=Max('task_logs__created_at')
    ).order_by('last_log').first()
    
    if oldest_solved:
        return oldest_solved
        
    return base_query.order_by('?').first()