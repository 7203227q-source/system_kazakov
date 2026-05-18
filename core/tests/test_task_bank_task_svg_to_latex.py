from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User


class TaskBankSvgToLatexTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pw", role="admin")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="0")
        self.variant = TaskVariant.objects.create(
            task=self.task,
            theme="classic",
            content='<p><img src="/formula/svg/1.svg" alt="x"/></p>',
            solution="",
        )

    def test_preview_does_not_persist(self):
        self.client.force_login(self.admin)
        url = reverse("task_bank_task_svg_to_latex_preview", args=[self.task.id])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.variant.refresh_from_db()
        self.assertIn("<img", self.variant.content)

    def test_apply_persists(self):
        self.client.force_login(self.admin)
        url = reverse("task_bank_task_svg_to_latex_apply", args=[self.task.id])
        res = self.client.post(url)
        self.assertEqual(res.status_code, 302)
        self.variant.refresh_from_db()
        self.assertNotIn("<img", self.variant.content)
        self.assertIn("$", self.variant.content)

