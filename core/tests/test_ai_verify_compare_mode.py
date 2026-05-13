import json
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, OpenRouterModel, Subject, SubjectAIConfig, Submission, Task, TaskType, Topic, User


class AIVerifyCompareModeTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=20, name="Тип 20", max_points=2)
        topic = Topic.objects.create(subject=self.subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)

        self.sub = Submission.objects.create(student=self.student, task=self.task, is_correct=None)
        self.sub.image_url = SimpleUploadedFile("a.jpg", b"fake", content_type="image/jpeg")
        self.sub.save()

        self.m1 = OpenRouterModel.objects.create(code="m1", label="M1", capabilities="vision", is_active=True)
        self.m2 = OpenRouterModel.objects.create(code="m2", label="M2", capabilities="vision", is_active=True)
        self.m3 = OpenRouterModel.objects.create(code="m3", label="M3", capabilities="vision", is_active=True)
        self.m4 = OpenRouterModel.objects.create(code="m4", label="M4", capabilities="vision", is_active=True)
        self.m5 = OpenRouterModel.objects.create(code="m5", label="M5", capabilities="vision", is_active=True)
        SubjectAIConfig.objects.create(
            subject=self.subject,
            photo_analysis_model=self.m1,
            photo_compare_model_1=self.m1,
            photo_compare_model_2=self.m2,
            photo_compare_model_3=self.m3,
            photo_compare_model_4=self.m4,
            photo_compare_model_5=self.m5,
        )

    def test_compare_returns_5_results_and_does_not_mutate_submission(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        dummy = {
            "choices": [
                {"message": {"content": json.dumps({"primary_score": 1, "is_correct": False, "feedback": "ok"})}}
            ]
        }

        from unittest.mock import patch

        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy

            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.sub.id]) + "?mode=compare")

        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["mode"], "compare")
        self.assertEqual(len(payload["results"]), 5)
        self.assertEqual(post.call_count, 5)

        self.sub.refresh_from_db()
        self.assertIsNone(self.sub.primary_score)
        self.assertIsNone(self.sub.ai_feedback)
        self.assertIsNone(self.sub.is_correct)

