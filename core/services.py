from datetime import datetime, timedelta

from django.db import models
from django.utils import timezone
import random
import time

from .fsrs_engine import review_card
from .models import ExamFormat, SpacedRepetition, TaskLog, TaskType

def ai_classify_task(task_content, subject):
    """
    Mock-сервис для классификации задания с помощью ИИ.
    В реальном проекте здесь будет вызов OpenAI API или YandexGPT
    с промптом вида: "Определи, к какому номеру задания ЕГЭ/ОГЭ относится этот текст".
    """
    # Эмулируем задержку нейросети
    time.sleep(0.5)
    
    content_lower = task_content.lower()
    
    # Пытаемся найти актуальный формат экзамена для предмета
    current_format = ExamFormat.objects.filter(subject=subject, is_active=True).first()
    if not current_format:
        return None
        
    # Простейшая эвристика для мока (ключевые слова)
    detected_number = None
    
    if "уравнен" in content_lower and "корень" in content_lower:
        detected_number = 1 # Простейшие уравнения (обычно №1 или №5 в профиле)
    elif "вероятност" in content_lower:
        detected_number = 4 # Вероятность
    elif "производн" in content_lower:
        detected_number = 8 # Производная
    elif "треугольник" in content_lower or "окружност" in content_lower:
        detected_number = 1 # Планиметрия
    else:
        # Если не смогли определить, выбираем случайный тип из существующих
        types = list(current_format.task_types.all())
        if types:
            return random.choice(types)
        return None
        
    # Ищем или создаем тип задания в базе
    task_type, _ = TaskType.objects.get_or_create(
        exam_format=current_format,
        number=detected_number,
        defaults={'name': f'Тип {detected_number} (определено ИИ)'}
    )
    
    return task_type

def normalize_active_time_seconds(value):
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return min(seconds, 60 * 60)


def get_expected_time_seconds(student):
    avg = (
        TaskLog.objects.filter(student=student, is_anomaly=False, time_spent__gt=0)
        .aggregate(a=models.Avg("time_spent"))
        .get("a")
    )
    if not avg:
        avg = (
            TaskLog.objects.filter(is_anomaly=False, time_spent__gt=0)
            .aggregate(a=models.Avg("time_spent"))
            .get("a")
        )
    return int(avg or 60)


def determine_fsrs_signal(*, is_correct, active_time_seconds, attempt_count, expected_time_seconds):
    if not is_correct:
        return "again"
    if int(attempt_count or 1) > 1:
        return "hard"
    if active_time_seconds is None:
        return "good"
    relative_time = float(active_time_seconds) / float(max(expected_time_seconds, 1))
    if relative_time >= 1.75:
        return "hard"
    return "good"


def process_srs_review(srs_record, grade, *, active_time_seconds=None, attempt_count=1):
    """Обновляет запись интервального повторения через FSRS-обертку."""
    try:
        return _process_fsrs_review(
            srs_record,
            grade=grade,
            active_time_seconds=active_time_seconds,
            attempt_count=attempt_count,
        )
    except Exception:
        srs_record.last_grade = int(grade)
        srs_record.last_reviewed_at = timezone.now()
        srs_record.next_review_date = timezone.localdate() + timedelta(days=1)
        srs_record.save(update_fields=["last_grade", "last_reviewed_at", "next_review_date"])
        return srs_record


def _process_fsrs_review(srs_record, *, grade, active_time_seconds=None, attempt_count=1):
    is_correct = int(grade) >= 3
    expected_time_seconds = get_expected_time_seconds(srs_record.student)
    normalized_time = normalize_active_time_seconds(active_time_seconds)
    signal = determine_fsrs_signal(
        is_correct=is_correct,
        active_time_seconds=normalized_time,
        attempt_count=attempt_count,
        expected_time_seconds=expected_time_seconds,
    )

    next_state = review_card(srs_record.fsrs_state, signal)
    due_dt = datetime.fromisoformat(next_state["due"])
<<<<<<< HEAD
=======
    today = timezone.localdate()
    due_date = due_dt.date()
    if due_date <= today:
        due_date = today + timedelta(days=1)
>>>>>>> trae/solo-agent-a9Fte2

    srs_record.srs_algorithm = "fsrs"
    srs_record.fsrs_state = next_state
    srs_record.last_grade = int(grade)
    srs_record.last_reviewed_at = timezone.now()
<<<<<<< HEAD
    srs_record.next_review_date = due_dt.date()
=======
    srs_record.next_review_date = due_date
>>>>>>> trae/solo-agent-a9Fte2
    srs_record.save(
        update_fields=[
            "srs_algorithm",
            "fsrs_state",
            "last_grade",
            "last_reviewed_at",
            "next_review_date",
        ]
    )

    return srs_record

def process_task_submission(student, task, grade, *, active_time_seconds=None, attempt_count=1):
    """
    Обрабатывает ответ ученика на задание: создает или обновляет
    запись интервального повторения.
    """
    srs_record, created = SpacedRepetition.objects.get_or_create(
        student=student,
        task=task,
        defaults={
            'easiness_factor': 2.5,
            'interval': 0,
            'repetitions': 0,
            'next_review_date': timezone.now().date(),
            'srs_algorithm': 'fsrs',
            'fsrs_state': {},
        }
    )

    return process_srs_review(
        srs_record,
        grade,
        active_time_seconds=active_time_seconds,
        attempt_count=attempt_count,
    )

def get_due_tasks_for_student(student, *, subject_id: int | None = None):
    """Возвращает записи интервального повторения, которые нужно повторить сегодня или ранее.

    Если указан subject_id, очередь ограничивается задачами этого предмета.
    """
    qs = SpacedRepetition.objects.filter(
        student=student,
        next_review_date__lte=timezone.now().date(),
        is_suspended=False,
    )
    if subject_id:
        qs = qs.filter(task__topic__subject_id=int(subject_id))
    return qs.order_by("next_review_date")
