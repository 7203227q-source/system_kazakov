import base64
import json
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, OpenRouterModel, Subject, SubjectAIConfig, Submission, Task, TaskType, TaskVariant, Topic, User


class SubmissionVerifyOpenRouterTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        self.task_type = TaskType.objects.create(exam_format=self.exam_format, number=20, name="Тип 20", max_points=2)
        self.topic = Topic.objects.create(subject=self.subject, name="Задания из Открытого Банка")
        self.task = Task.objects.create(
            fipi_id="X1",
            topic=self.topic,
            task_type=self.task_type,
            correct_answer="1",
            difficulty=10,
            exam_points=2,
        )
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        self.student = User.objects.create_user(username="st1", email="st1@example.com", password="pass", role="student")

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        self.submission = Submission.objects.create(student=self.student, task=self.task, image_url=image)

        model_obj = OpenRouterModel.objects.create(code="google/gemini-2.0-flash", label="Gemini 2.0 Flash", capabilities="vision")
        SubjectAIConfig.objects.create(subject=self.subject, photo_analysis_model=model_obj)

    def test_verify_uses_openrouter_when_configured(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        dummy_response = {
            "choices": [
                {"message": {"content": json.dumps({"primary_score": 1, "is_correct": True, "feedback": "ok"})}}
            ]
        }

        from unittest.mock import patch
        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response

            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.submission.id]))

        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["primary_score"], 1)
        self.assertTrue(payload["is_correct"])
        self.assertEqual(payload["model"], "google/gemini-2.0-flash")
