from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User


class SvgToLatexFormulaSvgSrcTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pass", role="admin")
        self.client.login(username="admin", password="pass")

    def test_converts_formula_svg_src(self):
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2024, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания")
        task_type = TaskType.objects.create(exam_format=exam_format, number=15, name="Тип 15", max_points=1)
        task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="1", difficulty=50, exam_points=1)

        html = '<p>Угол: <img src="/formula/svg/123" alt="26градусов"></p>'
        TaskVariant.objects.create(task=task, theme="classic", content=html, solution="")

        res = self.client.post(
            reverse("admin_svg_to_latex_convert"),
            {"exam_format": str(exam_format.id), "type_number": "15"},
        )
        self.assertEqual(res.status_code, 302)

        v = TaskVariant.objects.get(task=task, theme="classic")
        self.assertNotIn("<img", v.content)
        self.assertIn(r"^{\circ}", v.content)

    def test_converts_formula_generic_src(self):
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2024, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания")
        task_type = TaskType.objects.create(exam_format=exam_format, number=15, name="Тип 15", max_points=1)
        task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="1", difficulty=50, exam_points=1)

        html = '<p>Угол: <img src="/formula/123" alt="26градусов"></p>'
        TaskVariant.objects.create(task=task, theme="classic", content=html, solution="")

        res = self.client.post(
            reverse("admin_svg_to_latex_convert"),
            {"exam_format": str(exam_format.id), "type_number": "15"},
        )
        self.assertEqual(res.status_code, 302)

        v = TaskVariant.objects.get(task=task, theme="classic")
        self.assertNotIn("<img", v.content)
        self.assertIn(r"^{\circ}", v.content)
