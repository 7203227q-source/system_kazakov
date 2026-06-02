import datetime
from django.utils import timezone
from django.db.models import Avg, F, Count, Max, Q
from .models import TaskLog, DailySnapshot, StudentSubjectProfile, Submission, Assignment, Task, Topic
import random

ALPHA = 0.25  # Коэффициент экспоненциального сглаживания (EMA)

def touch_subject_streak(student, subject, *, today=None):
    """
    Обновляет стрик по предмету (StudentSubjectProfile) 1 раз в день.
    Правило: любая попытка решить задачу по предмету засчитывает день.
    """
    today = today or timezone.now().date()
    profile, _ = StudentSubjectProfile.objects.get_or_create(student=student, subject=subject)
    last = profile.last_streak_date

    if last == today:
        return profile

    if last == (today - datetime.timedelta(days=1)):
        profile.current_streak = int(profile.current_streak or 0) + 1
    else:
        profile.current_streak = 1

    profile.last_streak_date = today
    profile.save(update_fields=["current_streak", "last_streak_date"])

    # Поддерживаем legacy-поле на User: глобальный стрик = max по предметам
    mx = (
        StudentSubjectProfile.objects.filter(student=student)
        .aggregate(m=Max("current_streak"))
        .get("m")
        or 0
    )
    if int(student.current_streak or 0) != int(mx):
        student.current_streak = int(mx)
        student.save(update_fields=["current_streak"])

    return profile


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
    elif submission:
        if getattr(submission, "tutor_primary_score", None) is not None:
            score = float(submission.tutor_primary_score)
        elif submission.primary_score:
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

    # Стрик по предмету засчитывается при любой попытке (через запись лога)
    touch_subject_streak(student, task.topic.subject)
    
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
    
    current_mastery = None
    
    for log in recent_logs:
        # Нормализуем score задачи к 100-балльной шкале (условно, 1 балл = 100% успеха для задачи в 1 балл)
        # Если задача стоит 2 балла, и ученик получил 1, то это 50%
        max_points = float(log.task.exam_points)
        task_success_rate = (log.score / max_points * 100) if max_points > 0 else 0.0
        
        # Если это верифицированная сессия, даем ей больший вес (Trust Score = 1.0 vs 0.6)
        weight = 1.0 if log.is_verified else profile.trust_factor
        
        effective_score = task_success_rate * weight
        
        if current_mastery is None:
            current_mastery = effective_score
        else:
            current_mastery = (effective_score * ALPHA) + (float(current_mastery) * (1 - ALPHA))
            
    # 2. Обновление Daily Snapshot
    today = timezone.now().date()
    snapshot, created = DailySnapshot.objects.get_or_create(
        student=student,
        subject=subject,
        date=today
    )
    
    # 3. Расчет прогноза (Простая линейная экстраполяция для MVP)
    # Predicted Score = Current Mastery * Learning Velocity
    # --- Hybrid forecast (EMA mastery + recent performance) ---
    # current_mastery уже включает trust_factor (verified=1.0, unverified=trust_factor).
    # Добавляем "текущий перформанс" как отдельный сигнал без сильного занижения trust_factor:
    # это позволяет прогнозу реагировать на стабильный текущий результативный перформанс.
    perf_logs = list(
        TaskLog.objects.filter(
            student=student,
            task__topic__subject=subject,
            is_anomaly=False,
        )
        .select_related("task")
        .order_by("-created_at")[:30]
    )
    recent_perf = None
    if perf_logs:
        total_w = 0.0
        total = 0.0
        for log in perf_logs:
            max_points = float(getattr(log.task, "exam_points", 0) or 0.0)
            pct = (float(log.score or 0.0) / max_points * 100.0) if max_points > 0 else 0.0
            w = 1.0 if log.is_verified else 0.8
            total += pct * w
            total_w += w
        recent_perf = (total / total_w) if total_w > 0 else None

    blended_mastery = float(current_mastery)
    perf_delta = 0.0
    if recent_perf is not None:
        blended_mastery = 0.7 * float(current_mastery) + 0.3 * float(recent_perf)
        perf_delta = float(recent_perf) - float(current_mastery)

    predicted_score = blended_mastery * float(profile.learning_velocity or 1.0)

    def _clamp(x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, x))

    exam_date = getattr(profile, "exam_date", None)
    if exam_date and exam_date >= today:
        days_left = (exam_date - today).days
        if days_left > 0:
            start = today - datetime.timedelta(days=14)
            hist = list(
                DailySnapshot.objects.filter(student=student, subject=subject, date__gte=start, date__lt=today)
                .order_by("date")
                .values_list("date", "current_mastery")
            )
            if len(hist) >= 2:
                d0, m0 = hist[0]
                d1, m1 = hist[-1]
                span = max(1, (d1 - d0).days)
                slope = (float(m1 or 0.0) - float(m0 or 0.0)) / float(span)
                # Если текущий перформанс выше/ниже мастерства — усиливаем/ослабляем тренд.
                slope *= (1.0 + _clamp(perf_delta / 50.0, -0.5, 0.5))
                projected_mastery = float(blended_mastery) + slope * float(days_left)
                predicted_score = projected_mastery * float(profile.learning_velocity or 1.0)

    predicted_score = _clamp(float(predicted_score), 0.0, 100.0)
    
    snapshot.current_mastery = round(float(current_mastery or 0.0), 2)
    snapshot.predicted_exam_score = round(predicted_score, 2)
    
    # 4. Анализ разрыва (Gap Analysis)
    def _avg_score_pct(qs):
        logs = list(qs.select_related("task").order_by("-created_at")[:100])
        if not logs:
            return 0.0
        total = 0.0
        n = 0
        for log in logs:
            max_points = float(getattr(log.task, "exam_points", 0) or 0.0)
            if max_points <= 0:
                continue
            total += (float(log.score or 0.0) / max_points) * 100.0
            n += 1
        return (total / float(n)) if n > 0 else 0.0

    solo_avg = _avg_score_pct(
        TaskLog.objects.filter(
            student=student,
            task__topic__subject=subject,
            is_verified=False,
            is_anomaly=False,
        )
    )
    verified_avg = _avg_score_pct(
        TaskLog.objects.filter(
            student=student,
            task__topic__subject=subject,
            is_verified=True,
            is_anomaly=False,
        )
    )

    if verified_avg > 0 and solo_avg > 0:
        gap = float(solo_avg) - float(verified_avg)
        snapshot.gap_between_solo_and_verified = round(gap, 2)

        if gap > 30.0:
            profile.trust_factor = max(0.1, float(profile.trust_factor) - 0.05)
        elif gap < 10.0:
            profile.trust_factor = min(1.0, float(profile.trust_factor) + 0.05)
            
    snapshot.save()
    profile.save(update_fields=['trust_factor'])
    
    return snapshot


def calibrate_learning_velocity_for_assignment(assignment: Assignment) -> bool:
    """
    Калибрует StudentSubjectProfile.learning_velocity по завершённому варианту.

    Возвращает True, если калибровка была применена, иначе False.
    """
    if not assignment or not getattr(assignment, "is_completed", False):
        return False

    # Не калибруем дважды по одному варианту.
    if getattr(assignment, "learning_velocity_calibrated_at", None):
        return False

    student = assignment.student
    subject = None
    if getattr(assignment, "exam_format_id", None):
        subject = getattr(assignment.exam_format, "subject", None)
    if subject is None:
        # fallback: берём предмет первой задачи
        first_task = assignment.tasks.select_related("topic__subject").first()
        subject = getattr(getattr(first_task, "topic", None), "subject", None)
    if subject is None:
        return False

    profile = StudentSubjectProfile.objects.filter(student=student, subject=subject).first()
    if profile is None:
        return False

    today = timezone.now().date()
    # Берём "прогноз до выполнения работы", чтобы избежать нулевой ошибки (волатильности):
    # если мы возьмём snapshot "сегодня", он уже может включать результаты текущего варианта.
    snapshot = (
        DailySnapshot.objects.filter(student=student, subject=subject, date__lt=today)
        .order_by("-date")
        .first()
        or DailySnapshot.objects.filter(student=student, subject=subject, date__lte=today).order_by("-date").first()
    )
    if snapshot is None:
        return False

    predicted = float(getattr(snapshot, "predicted_exam_score", 0.0) or 0.0)

    # Фактический результат варианта: сумма первичных баллов / max_primary_score.
    subs = Submission.objects.filter(assignment=assignment, student=student)
    earned = 0.0
    for sub in subs:
        if sub.tutor_primary_score is not None:
            earned += float(sub.tutor_primary_score or 0.0)
        elif sub.primary_score is not None:
            earned += float(sub.primary_score or 0.0)
        elif sub.score is not None:
            earned += float(sub.score or 0.0)

    max_primary = None
    try:
        if assignment.exam_format_id and getattr(assignment.exam_format, "score_scale", None):
            max_primary = float(getattr(assignment.exam_format.score_scale, "max_primary_score", None) or 0.0) or None
    except Exception:
        max_primary = None

    if not max_primary:
        # fallback: сумма max_points по типам (или exam_points)
        max_primary = 0.0
        for t in assignment.tasks.select_related("task_type").all():
            pts = getattr(getattr(t, "task_type", None), "max_points", None)
            if pts is None:
                pts = getattr(t, "exam_points", 0) or 0
            max_primary += float(pts or 0.0)

    if not max_primary or max_primary <= 0:
        return False

    fact = max(0.0, min(100.0, 100.0 * float(earned) / float(max_primary)))
    err = float(fact) - float(predicted)

    # Смешанная стратегия:
    # - в начале (нет 3 контрольных калибровок) пропускаем неконтрольные варианты
    # - позже учитываем неконтрольные с меньшим весом и с учётом trust_factor
    verified_calibrations = Assignment.objects.filter(
        student=student,
        exam_format__subject=subject,
        is_verified=True,
        learning_velocity_calibrated_at__isnull=False,
    ).count()
    if not assignment.is_verified and verified_calibrations < 3:
        return False

    base_weight = 1.0 if assignment.is_verified else (0.5 * float(getattr(profile, "trust_factor", 0.6) or 0.6))

    # Базовый коэффициент (насколько быстро адаптируемся к err).
    k = 0.25
    delta = (k * err) / 100.0

    # Ограничение шага за один пересчёт.
    delta = max(-0.10, min(0.10, float(delta)))

    # Прогрев (warm-up): первые калибровки — заметно мягче.
    n = Assignment.objects.filter(
        student=student,
        exam_format__subject=subject,
        learning_velocity_calibrated_at__isnull=False,
    ).count()
    warmup = 1.0
    if n < 5:
        warmup = 0.3
    elif n < 10:
        warmup = 0.6

    # Дедлайны: сильный штраф (снижаем влияние результата).
    deadline_weight = 1.0
    if getattr(assignment, "is_expired", False):
        deadline_weight = 0.2
    else:
        due = getattr(assignment, "due_date", None)
        if due and today > due:
            deadline_weight = 0.2

    delta *= float(base_weight) * float(warmup) * float(deadline_weight)

    old_lv = float(getattr(profile, "learning_velocity", 1.0) or 1.0)
    new_lv = old_lv + float(delta)
    new_lv = max(0.5, min(1.5, float(new_lv)))

    profile.learning_velocity = float(new_lv)
    profile.save(update_fields=["learning_velocity"])

    assignment.learning_velocity_calibrated_at = timezone.now()
    assignment.save(update_fields=["learning_velocity_calibrated_at"])
    return True

def get_adaptive_task_for_student(student, subject_id: int | None = None, exam_format_id: int | None = None):
    """
    Алгоритм интервального повторения (Адаптивный Тренажер).
    Детализированный уровень: Topic + task_type + конкретные затыки.
    """
    active_subjects = list(student.subject_profiles.values_list('subject_id', flat=True))
    
    if not active_subjects:
        return Task.objects.order_by('?').first()

    # Явный выбор предмета (из UI тренажёра)
    if subject_id is not None:
        try:
            subject_id = int(subject_id)
        except Exception:
            subject_id = None
    if subject_id is None or subject_id not in active_subjects:
        subject_id = active_subjects[0]

    # Ограничиваем по формату экзамена, выбранному в профиле ученика (если есть)
    if exam_format_id is None:
        try:
            prof = student.subject_profiles.filter(subject_id=subject_id).select_related("exam_format").first()
            if prof and prof.exam_format_id:
                exam_format_id = int(prof.exam_format_id)
        except Exception:
            exam_format_id = None
    if exam_format_id is None:
        try:
            from core.models import ExamFormat
            ef = ExamFormat.objects.filter(subject_id=subject_id, is_active=True).order_by("-year", "name").first()
            if ef:
                exam_format_id = int(ef.id)
        except Exception:
            exam_format_id = None

    base_tasks_all = Task.objects.filter(topic__subject_id=subject_id)
    if exam_format_id is not None:
        base_tasks_all = base_tasks_all.filter(task_type__exam_format_id=exam_format_id)
        
    # 1. Группируем по уникальным парам (topic_id, task_type)
    # Используем модель Task как базовую для агрегации
    subtopics = base_tasks_all.values('topic_id', 'task_type').annotate(
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
    base_query = base_tasks_all.filter(
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
