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


class AIVerdictAntiFraudAndBreakdownTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        self.task_type = TaskType.objects.create(
            exam_format=self.exam_format,
            number=20,
            name="Тип 20",
            max_points=2,
            is_extended_answer=True,
        )
        self.topic = Topic.objects.create(subject=self.subject, name="T")
        self.task = Task.objects.create(
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

        model_obj = OpenRouterModel.objects.create(code="test-model", label="Test", capabilities="vision")
        SubjectAIConfig.objects.create(subject=self.subject, photo_analysis_model=model_obj)

        os.environ["OPENROUTER_API_KEY"] = "test"

    def test_forces_zero_when_photo_invalid_even_if_model_gives_points(self):
        structured = {
            "primary_score": 2,
            "is_correct": True,
            "photo_valid": False,
            "photo_valid_reason": "На фото не решение этой задачи.",
            "recognition_confidence": 0.9,
            "recognized_solution": "Похоже на кота.",
            "mistakes": [],
            "verdict": ["ОК"],
            "score_breakdown": [{"label": "К1", "awarded": 2, "max": 2, "reason": "ОК"}],
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
        self.assertEqual(data["primary_score"], 0)
        self.assertFalse(data["is_correct"])
        self.submission.refresh_from_db()
        self.assertEqual(int(self.submission.primary_score or 0), 0)
        self.assertFalse(bool(self.submission.is_correct))
        self.assertIn("На фото не решение", self.submission.ai_feedback or "")

    def test_forces_zero_when_confidence_below_threshold(self):
        structured = {
            "primary_score": 1,
            "is_correct": False,
            "photo_valid": True,
            "photo_valid_reason": "",
            "recognition_confidence": 0.1,
            "recognized_solution": "[неразборчиво]",
            "mistakes": [],
            "verdict": ["Неуверенность распознавания: высокая."],
            "score_breakdown": [{"label": "К1", "awarded": 1, "max": 2, "reason": "частично"}],
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
        self.assertEqual(data["primary_score"], 0)
        self.assertFalse(data["is_correct"])

    def test_normalizes_latex_in_recognized_solution_and_breakdown_reason(self):
        structured = {
            "primary_score": 1,
            "is_correct": False,
            "photo_valid": True,
            "photo_valid_reason": "",
            "recognition_confidence": 0.9,
            "recognized_solution": "frac12 + 1 = 3/2",
            "mistakes": ["Нужно написать frac12 корректно"],
            "verdict": ["Оценка: 1/2."],
            "score_breakdown": [{"label": "Ошибка 1", "awarded": 1, "max": 2, "reason": "frac12 не оформлен"}],
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
        self.assertIn("\\frac", data.get("recognized_solution") or "")
        sb = data.get("score_breakdown") or []
        self.assertTrue(sb)
        self.assertIn("\\frac", (sb[0].get("reason") or ""))
