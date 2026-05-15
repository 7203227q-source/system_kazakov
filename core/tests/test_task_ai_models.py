from django.test import TestCase

from core.models import Subject, ExamFormat, TaskType, Topic, Task


class TaskAIMetadataModelTests(TestCase):
    def test_task_has_ai_fields_defaults(self):
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")

        task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="1")
        self.assertTrue(hasattr(task, "ai_difficulty_raw"))
        self.assertIsNone(task.ai_difficulty_raw)
        self.assertIsNone(task.ai_difficulty_exam_percentile)
        self.assertIsNone(task.ai_difficulty_type_percentile)
