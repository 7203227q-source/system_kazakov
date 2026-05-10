import csv
import io
from .models import Task, TaskVariant, TaskType, Topic, ExamFormat
from .task_html import normalize_task_html
from .utils import download_and_replace_images

def import_tasks_from_csv(file_obj, exam_format_id):
    """
    Parses a CSV file and imports/updates Tasks and TaskVariants.
    Expected CSV columns:
    fipi_id, type_number, subtype_tag, difficulty, correct_answer, theme, content, solution
    """
    decoded_file = file_obj.read().decode('utf-8')
    io_string = io.StringIO(decoded_file)
    reader = csv.DictReader(io_string)

    exam_format = ExamFormat.objects.get(id=exam_format_id)
    topic = Topic.objects.get_or_create(subject=exam_format.subject, name="Задания из Открытого Банка")[0]

    created_tasks = 0
    updated_tasks = 0

    for row in reader:
        fipi_id = row.get('fipi_id', '').strip()
        if not fipi_id:
            continue

        type_number = int(row.get('type_number', 1))
        subtype_tag = row.get('subtype_tag', '').strip()
        difficulty = int(row.get('difficulty', 50))
        correct_answer = row.get('correct_answer', '').strip()
        theme = row.get('theme', 'classic').strip()
        content = row.get('content', '').strip()
        solution = row.get('solution', '').strip()

        task_type, _ = TaskType.objects.get_or_create(
            exam_format=exam_format,
            number=type_number,
            defaults={'name': f"Тип {type_number}"}
        )

        task, created = Task.objects.update_or_create(
            fipi_id=fipi_id,
            defaults={
                'topic': topic,
                'task_type': task_type,
                'subtype_tag': subtype_tag,
                'difficulty': difficulty,
                'correct_answer': correct_answer,
                'exam_points': task_type.max_points
            }
        )

        if created:
            created_tasks += 1
        else:
            updated_tasks += 1

        # Process images and HTML content
        processed_content = download_and_replace_images(content, fipi_id, theme, segment="content")
        processed_solution = download_and_replace_images(solution, fipi_id, theme, segment="solution")
        processed_content = normalize_task_html(processed_content)
        processed_solution = normalize_task_html(processed_solution)

        # Update or create variant
        TaskVariant.objects.update_or_create(
            task=task,
            theme=theme,
            defaults={
                'content': processed_content,
                'solution': processed_solution
            }
        )

    return created_tasks, updated_tasks
