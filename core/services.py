from datetime import datetime
from django.utils import timezone
from .models import SpacedRepetition, TaskType, ExamFormat
from .fsrs_engine import review_card
import random
import time

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

def _fsrs_label_from_grade(grade):
    return "good" if int(grade) >= 3 else "again"


def process_srs_review(srs_record, grade, *, active_time_seconds=None, attempt_count=1):
    """
    Обновляет запись интервального повторения через FSRS-обертку.
    """
    del active_time_seconds, attempt_count

    next_state = review_card(srs_record.fsrs_state, _fsrs_label_from_grade(grade))
    due_dt = datetime.fromisoformat(next_state["due"])

    srs_record.srs_algorithm = "fsrs"
    srs_record.fsrs_state = next_state
    srs_record.last_grade = int(grade)
    srs_record.last_reviewed_at = timezone.now()
    srs_record.next_review_date = due_dt.date()
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
