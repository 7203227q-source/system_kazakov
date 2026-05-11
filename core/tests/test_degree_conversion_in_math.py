from django.test import TestCase

from core.models import ExamFormat, Subject, Task, TaskType, Topic, TaskVariant


class DegreeConversionInMathTests(TestCase):
    def test_degree_word_inside_math_converts(self):
        subject = Subject.objects.create(name="Математика")
        fmt = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=fmt, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Т")
        task = Task.objects.create(topic=topic, task_type=tt, subtype_tag="x", correct_answer="1", difficulty=10, exam_points=1)
        TaskVariant.objects.create(task=task, theme="classic", content=r"$\angle BAC = 26градусов$", solution="")

        out = task.get_content_for_theme()
        self.assertIn(r"26^{\circ}", out)
        self.assertNotIn("градусов", out)
