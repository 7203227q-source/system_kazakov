from django.test import TestCase

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User
from core.services_svg_to_latex import convert_svg_to_latex_for_task_type


class SvgToLatexDebugStatsTests(TestCase):
    def test_reports_degree_candidates(self):
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2024, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания")
        task_type = TaskType.objects.create(exam_format=exam_format, number=15, name="Тип 15", max_points=1)
        task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="1", difficulty=50, exam_points=1)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>$48 градусов$</p>", solution="")

        res = convert_svg_to_latex_for_task_type(exam_format_id=exam_format.id, type_number=15, theme="classic", dry_run=True)
        self.assertEqual(res["scanned"], 1)
        self.assertGreaterEqual(res.get("deg_candidates", 0), 1)

