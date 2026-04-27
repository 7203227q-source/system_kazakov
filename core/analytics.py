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
    Выбирает наиболее подходящую задачу для ученика на основе:
    1. Ошибок в прошлых попытках.
    2. Времени, прошедшего с последней попытки по теме (Кривая забывания).
    3. Новых тем, которые еще не решались.
    """
    # Получаем предметы, которые ученик добавил в профиль
    active_subjects = student.subject_profiles.values_list('subject_id', flat=True)
    
    # Если предметов нет, берем просто случайную задачу из базы
    if not active_subjects:
        return Task.objects.order_by('?').first()
        
    # 1. Собираем статистику по темам
    topics = Topic.objects.filter(subject_id__in=active_subjects).annotate(
        last_practiced=Max('tasks__task_logs__created_at', filter=Q(tasks__task_logs__student=student)),
        total_attempts=Count('tasks__task_logs', filter=Q(tasks__task_logs__student=student)),
        # Упрощенно: считаем долю правильных решений (для задач с 1 баллом). 
        # Если score > 0, считаем правильным
        correct_attempts=Count('tasks__task_logs', filter=Q(tasks__task_logs__student=student, tasks__task_logs__score__gt=0))
    )
    
    now = timezone.now()
    topic_priorities = []
    
    for topic in topics:
        priority = 0.0
        
        if topic.total_attempts == 0:
            # Новая тема - высокий приоритет, чтобы ученик прошел весь материал
            priority = 2.0
        else:
            # 2. Фактор забывания (Forgetting Factor)
            days_since = (now - topic.last_practiced).days
            # Чем больше дней прошло, тем выше приоритет (капаем по 0.1 в день, максимум 1.5)
            forgetting_factor = min(1.5, days_since * 0.1)
            
            # 3. Фактор ошибок (Error Factor)
            accuracy = topic.correct_attempts / topic.total_attempts
            error_factor = 1.0 - accuracy # От 0.0 (всё решил верно) до 1.0 (всё решил неверно)
            
            # Если тема решена недавно и без ошибок, приоритет будет около 0
            priority = forgetting_factor + (error_factor * 1.5) # Ошибки важнее
            
        topic_priorities.append({
            'topic': topic,
            'priority': priority
        })
        
    if not topic_priorities:
        return Task.objects.order_by('?').first()
        
    # Сортируем темы по приоритету (по убыванию)
    topic_priorities.sort(key=lambda x: x['priority'], reverse=True)
    
    # Берем Топ-3 тем, чтобы добавить случайности
    top_topics = [item['topic'] for item in topic_priorities[:3]]
    selected_topic = random.choice(top_topics)
    
    # 4. Выбор задачи внутри темы
    # Ищем задачу, которую ученик еще не решал правильно
    unsolved_tasks = Task.objects.filter(topic=selected_topic).exclude(
        task_logs__student=student, task_logs__score__gt=0
    )
    
    if unsolved_tasks.exists():
        return unsolved_tasks.order_by('?').first()
        
    # Если все задачи решены правильно, берем ту, которую он решал дольше всего назад
    oldest_solved_task = Task.objects.filter(topic=selected_topic, task_logs__student=student).annotate(
        last_log=Max('task_logs__created_at')
    ).order_by('last_log').first()
    
    if oldest_solved_task:
        return oldest_solved_task
        
    # Fallback
    return Task.objects.filter(topic=selected_topic).order_by('?').first()