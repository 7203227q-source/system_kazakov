import base64
import json
import os
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, OpenRouterModel, Subject, SubjectAIConfig, Submission, Task, TaskType, TaskVariant, Topic, User


class AIVerifyRetryCooldownTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=20, name="Тип 20", max_points=2, is_extended_answer=True)
        topic = Topic.objects.create(subject=self.subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        self.sub = Submission.objects.create(student=self.student, task=self.task, image_url=image)

        m = OpenRouterModel.objects.create(code="m1", label="M1", capabilities="vision", is_active=True)
        SubjectAIConfig.objects.create(subject=self.subject, photo_analysis_model=m)

    def test_rate_limited_with_retry_after(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        # Эмулируем, что проверка только что была
        self.sub.ai_last_verify_at = timezone.now()
        self.sub.save(update_fields=["ai_last_verify_at"])

        self.client.force_login(self.student)
        res = self.client.post(reverse("api_verify_with_ai", args=[self.sub.id]))
        self.assertEqual(res.status_code, 429)
        data = res.json()
        self.assertEqual(data.get("error"), "ai_retry_later")
        self.assertTrue(int(data.get("retry_after") or 0) > 0)

    def test_allowed_after_2_minutes_even_if_already_checked(self):
        os.environ["OPENROUTER_API_KEY"] = "test"
        self.sub.is_correct = False
        self.sub.ai_feedback = "old"
        self.sub.ai_last_verify_at = timezone.now() - timedelta(seconds=121)
        self.sub.save(update_fields=["is_correct", "ai_feedback", "ai_last_verify_at"])

        dummy = {"choices": [{"message": {"content": json.dumps({"primary_score": 1, "is_correct": False, "feedback": "new"})}}]}

        from unittest.mock import patch
        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy

            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.sub.id]))

        self.assertEqual(res.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.primary_score, 1)
        self.assertEqual(self.sub.ai_feedback, "new")

