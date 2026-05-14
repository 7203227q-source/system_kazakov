import json
import os

from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import (
    Assignment,
    ExamFormat,
    OpenRouterModel,
    Subject,
    SubjectAIConfig,
    Submission,
    Task,
    TaskType,
    Topic,
    User,
)


class TutorVerifyAiCooldownTests(TestCase):
    def setUp(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor.students.add(self.student)

        subj = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subj, name="T")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)

        model = OpenRouterModel.objects.create(code="test-model", label="Test", is_active=True)
        SubjectAIConfig.objects.create(subject=subj, photo_analysis_model=model)

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=ef)
        self.assignment.tasks.add(self.task)
        # минимальный валидный PNG (1x1)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xa6\x18\xdd\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        self.sub = Submission.objects.create(student=self.student, task=self.task, assignment=self.assignment, image_url=image)

    def test_tutor_verify_ai_has_cooldown(self):
        self.client.login(username="t", password="pass")
        url = reverse("api_tutor_verify_with_ai", args=[self.sub.id])

        from unittest.mock import patch

        dummy_response = {
            "choices": [
                {"message": {"content": json.dumps({"primary_score": 1, "is_correct": False, "feedback": "ok"})}}
            ]
        }
        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response

            r1 = self.client.post(url)
            self.assertEqual(r1.status_code, 200, r1.content)
            r2 = self.client.post(url)
            self.assertEqual(r2.status_code, 429)
