import base64
import json
import os
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, OpenRouterModel, SpacedRepetition, Subject, SubjectAIConfig, Submission, Task, TaskType, TaskVariant, Topic, User


class AIVerifyPartialScoreAddsSrsTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        topic = Topic.objects.create(subject=self.subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        self.submission = Submission.objects.create(student=self.student, task=self.task, image_url=image)

        m = OpenRouterModel.objects.create(code="m1", label="M1", capabilities="vision", is_active=True)
        SubjectAIConfig.objects.create(subject=self.subject, photo_analysis_model=m)

    def test_partial_score_creates_srs_record(self):
        os.environ["OPENROUTER_API_KEY"] = "test"
        dummy_response = {
            "choices": [{"message": {"content": json.dumps({"primary_score": 2, "is_correct": False, "feedback": "ok"})}}]
        }

        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response

            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.submission.id]))

        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(SpacedRepetition.objects.filter(student=self.student, task=self.task).exists())

    def test_ai_verify_passes_review_context_to_srs_processing(self):
        os.environ["OPENROUTER_API_KEY"] = "test"
        dummy_response = {
            "choices": [{"message": {"content": json.dumps({"primary_score": 2, "is_correct": False, "feedback": "ok"})}}]
        }

        with patch("core.views.requests.post") as post, patch("core.views.process_task_submission") as process_task_submission:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response

            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.submission.id]))

        self.assertEqual(res.status_code, 200, res.content)
        process_task_submission.assert_called_once_with(
            self.student,
            self.task,
            1,
            active_time_seconds=60,
            attempt_count=1,
        )
