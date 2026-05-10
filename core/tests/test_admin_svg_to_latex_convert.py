from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User


class AdminSvgToLatexConvertTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pass", role="admin")
        self.client.login(username="admin", password="pass")

    def test_converts_svg_images_for_type(self):
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        task_type = TaskType.objects.create(exam_format=exam_format, number=6, name="Тип 6", max_points=1)
        task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="1", difficulty=50, exam_points=1)

        alt = (
            "18 умножить на левая круглая скобка дробь: числитель: 1, знаменатель: 9 конец дроби "
            "правая круглая скобка в квадрате минус 20 умножить на дробь: числитель: 1, знаменатель: 9 конец дроби ."
        )
        html = f'<p>Найдите <img src="/media/tasks/x.svg" alt="{alt}"></p>'
        TaskVariant.objects.create(task=task, theme="classic", content=html, solution=html)

        res = self.client.post(
            reverse("admin_svg_to_latex_convert"),
            {"exam_format": str(exam_format.id), "type_number": "6"},
        )
        self.assertEqual(res.status_code, 302)

        v = TaskVariant.objects.get(task=task, theme="classic")
        self.assertIn("$", v.content)
        self.assertNotIn("<img", v.content)
        self.assertIn("$", v.solution)
        self.assertNotIn("<img", v.solution)

