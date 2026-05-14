import base64
import json
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, OpenRouterModel, Subject, SubjectAIConfig, Submission, Task, TaskType, TaskVariant, Topic, User


class SubmissionVerifyOpenRouterTwoImagesTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=20, name="Тип 20", max_points=2, is_extended_answer=True)
        topic = Topic.objects.create(subject=self.subject, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        self.student = User.objects.create_user(username="st1", email="st1@example.com", password="pass", role="student")

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image1 = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        image2 = SimpleUploadedFile("b.png", png_bytes, content_type="image/png")
        self.submission = Submission.objects.create(student=self.student, task=task, image_url=image1, image_url_2=image2)

        model_obj = OpenRouterModel.objects.create(code="m1", label="M1", capabilities="vision")
        SubjectAIConfig.objects.create(subject=self.subject, photo_analysis_model=model_obj)

    def test_verify_sends_both_images(self):
        os.environ["OPENROUTER_API_KEY"] = "test"
        dummy_response = {
            "choices": [{"message": {"content": json.dumps({"primary_score": 1, "is_correct": True, "feedback": "ok"})}}]
        }

        from unittest.mock import patch
        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response

            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.submission.id]))

        self.assertEqual(res.status_code, 200)
        sent_payload = post.call_args.kwargs["json"]
        user_msg = next(m for m in sent_payload["messages"] if m["role"] == "user")
        imgs = [p for p in user_msg["content"] if p["type"] == "image_url"]
        self.assertGreaterEqual(len(imgs), 2)

