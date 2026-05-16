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
        payload = res.json()
        self.assertEqual(payload["preview"]["correct_answer"], "0.175")
        self.assertTrue(bool(payload.get("preview_log_id")))

    def test_apply_uses_preview_log_id_and_does_not_regenerate(self):
        self.client.force_login(self.admin)
        preview_url = reverse("admin_task_regen_preview", args=[self.task.id])
        with patch("core.openrouter_client.generate_task_regeneration") as gen_preview:
            gen_preview.return_value = {
                "content_html": "<p>x</p>",
                "solution_html": "<p>y</p>",
                "correct_answer": "0.2917",
                "notes": "exact_fraction=7/40",
            }
            preview_res = self.client.post(
                preview_url,
                data=json.dumps({"mode": "full", "model": "m"}),
                content_type="application/json",
            )
        self.assertEqual(preview_res.status_code, 200)
        preview_log_id = preview_res.json().get("preview_log_id")
        self.assertTrue(bool(preview_log_id))

        apply_url = reverse("admin_task_regen_apply", args=[self.task.id])
        with patch("core.openrouter_client.generate_task_regeneration") as gen_apply:
            gen_apply.side_effect = AssertionError("generate_task_regeneration should not be called on apply")
            res = self.client.post(
                apply_url,
                data=json.dumps({"mode": "full", "model": "m", "preview_log_id": preview_log_id}),
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.correct_answer, "0.175")
