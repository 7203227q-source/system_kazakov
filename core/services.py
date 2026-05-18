from datetime import timedelta
from django.utils import timezone
from .models import SpacedRepetition, TaskType, ExamFormat
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

def process_srs_review(srs_record, grade):
    """
    Алгоритм SuperMemo-2 (SM-2) для интервального повторения.
    
    Параметры:
    - srs_record: объект SpacedRepetition
    - grade: оценка от 0 до 5
        0 - полная отключка (не вспомнил вообще)
        1 - неправильный ответ, но вспомнился при подсказке
        2 - неправильный ответ, где правильный казался легким
        3 - правильный ответ, но вспомнил с большим трудом
        4 - правильный ответ после раздумий
        5 - идеальный ответ, без задержек
    """
    if grade >= 3:
        if srs_record.repetitions == 0:
            srs_record.interval = 1
        elif srs_record.repetitions == 1:
            srs_record.interval = 6
        else:
            srs_record.interval = round(srs_record.interval * srs_record.easiness_factor)
        srs_record.repetitions += 1
    else:
        srs_record.repetitions = 0
        srs_record.interval = 1

    # Формула обновления E-Factor:
    # EF':= EF + (0.1 - (5-q)*(0.08 + (5-q)*0.02))
    srs_record.easiness_factor += (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
    if srs_record.easiness_factor < 1.3:
        srs_record.easiness_factor = 1.3

    srs_record.last_grade = grade
    srs_record.last_reviewed_at = timezone.now()
    # Дата следующего повторения
    srs_record.next_review_date = timezone.now().date() + timedelta(days=srs_record.interval)
    srs_record.save()
    
    return srs_record

def process_task_submission(student, task, grade):
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
        }
    )
    
    return process_srs_review(srs_record, grade)

def get_due_tasks_for_student(student):
    """Возвращает записи интервального повторения, которые нужно повторить сегодня или ранее"""
    return SpacedRepetition.objects.filter(
        student=student, 
        next_review_date__lte=timezone.now().date()
    ).order_by('next_review_date')
