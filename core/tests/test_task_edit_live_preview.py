import json

from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, Topic, User


class TaskEditLivePreviewEndpointTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pw", role="admin")
        self.tutor = User.objects.create_user(username="tutor", password="pw", role="tutor")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="0")

    def test_admin_can_render_preview_json(self):
        self.client.force_login(self.admin)
        url = reverse("task_bank_task_render_preview", args=[self.task.id])
        payload = {"content": '<p><img src="/formula/svg/1.svg" alt="x"/></p>', "solution": "<p>y</p>"}
        res = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("content_html", data)
        self.assertIn("solution_html", data)
        self.assertIn("<img", data["content_html"])

    def test_non_admin_is_redirected(self):
        self.client.force_login(self.tutor)
        url = reverse("task_bank_task_render_preview", args=[self.task.id])
        res = self.client.post(url, data=json.dumps({"content": "x", "solution": ""}), content_type="application/json")
        self.assertEqual(res.status_code, 302)

