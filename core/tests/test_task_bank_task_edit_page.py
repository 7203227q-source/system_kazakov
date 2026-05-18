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

