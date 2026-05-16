import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, Topic, User


class AdminTaskRegenExactAnswerTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pw", role="admin")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="0")

    @patch("core.openrouter_client.generate_task_regeneration")
    def test_preview_returns_normalized_correct_answer(self, gen):
        gen.return_value = {
            "content_html": "<p>x</p>",
            "solution_html": "<p>y</p>",
            "correct_answer": "0.2917",
            "notes": "exact_fraction=7/40",
        }

        self.client.force_login(self.admin)
        url = reverse("admin_task_regen_preview", args=[self.task.id])
        res = self.client.post(
            url,
            data=json.dumps({"mode": "full", "model": "m"}),
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["preview"]["correct_answer"], "0.175")

    @patch("core.openrouter_client.generate_task_regeneration")
    def test_apply_saves_normalized_correct_answer(self, gen):
        gen.return_value = {
            "content_html": "<p>x</p>",
            "solution_html": "<p>y</p>",
            "correct_answer": "0.2917",
            "notes": "exact_fraction=7/40",
        }

        self.client.force_login(self.admin)
        url = reverse("admin_task_regen_apply", args=[self.task.id])
        res = self.client.post(
            url,
            data=json.dumps({"mode": "full", "model": "m"}),
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.correct_answer, "0.175")

