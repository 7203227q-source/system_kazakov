import base64
import json
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import (
    ExamFormat,
    OpenRouterModel,
    Subject,
    SubjectAIConfig,
    Submission,
    Task,
    TaskType,
    TaskVariant,
    Topic,
    User,
)


class SubmissionVerifyOpenRouterStructuredTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        self.task_type = TaskType.objects.create(exam_format=self.exam_format, number=1, name="Тип 1", max_points=2)
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

    def test_verify_saves_structured_fields(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        structured = {
            "primary_score": 1,
            "is_correct": False,
            "recognized_solution": "1) Перенёс влево\n2) Сократил",
            "mistakes": ["На шаге 2 нельзя сокращать на 0", "Потерян знак минус"],
            "verdict": ["Оценка: 1/2.", "Рекомендация: перепроверь ОДЗ."],
            "feedback": "",
        }
        dummy_response = {"choices": [{"message": {"content": json.dumps(structured, ensure_ascii=False)}}]}

        from unittest.mock import patch

        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response

            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.submission.id]))

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["primary_score"], 1)
        self.assertFalse(data["is_correct"])
        self.assertEqual(data["recognized_solution"], structured["recognized_solution"])
        self.assertEqual(data["mistakes"], structured["mistakes"])
        self.assertEqual(data["verdict"], structured["verdict"])

        self.submission.refresh_from_db()
        self.assertTrue(self.submission.ai_recognized_solution)
        self.assertTrue(self.submission.ai_mistakes_json)
        self.assertTrue(self.submission.ai_verdict_json)
        self.assertIn("Решение (как распознано)", self.submission.ai_feedback or "")

    def test_verify_fallback_when_only_feedback_present(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        payload = {"primary_score": 2, "is_correct": True, "feedback": "Абзац 1.\n\nАбзац 2."}
        dummy_response = {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}

        from unittest.mock import patch

        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response

            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.submission.id]))

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["feedback"], payload["feedback"])
        self.assertEqual(data.get("recognized_solution"), "")
        self.assertEqual(data.get("mistakes"), [])
        self.assertEqual(data.get("verdict"), [])

