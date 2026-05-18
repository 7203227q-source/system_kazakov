from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User


class TaskBankEditButtonTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pw", role="admin")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="0")
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>x</p>", solution="<p>y</p>")

    def test_task_bank_has_edit_button_for_admin(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("tutor_task_bank"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("Редактировать", res.content.decode("utf-8"))
        self.assertIn(f"/tutor/tasks/{self.task.id}/edit/", res.content.decode("utf-8"))


class TaskBankEditPageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pw", role="admin")
        self.tutor = User.objects.create_user(username="tutor", password="pw", role="tutor")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="0")
        self.variant = TaskVariant.objects.create(task=self.task, theme="classic", content="<p>x</p>", solution="<p>y</p>")

    def test_edit_page_admin_only(self):
        self.client.force_login(self.tutor)
        res = self.client.get(reverse("task_bank_task_edit", args=[self.task.id]))
        self.assertEqual(res.status_code, 302)

        self.client.force_login(self.admin)
        res2 = self.client.get(reverse("task_bank_task_edit", args=[self.task.id]))
        self.assertEqual(res2.status_code, 200)
        self.assertIn("Редактирование задачи", res2.content.decode("utf-8"))

    def test_edit_page_updates_classic_variant(self):
        self.client.force_login(self.admin)
        url = reverse("task_bank_task_edit", args=[self.task.id])
        res = self.client.post(url, data={"content": "<p>new</p>", "solution": "<p>sol</p>"})
        self.assertEqual(res.status_code, 302)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.content, "<p>new</p>")
        self.assertEqual(self.variant.solution, "<p>sol</p>")
