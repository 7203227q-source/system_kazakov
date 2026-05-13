import base64
import json
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, OpenRouterModel, Subject, SubjectAIConfig, Submission, Task, TaskType, TaskVariant, Topic, User


class AIVerifyRepairsInvalidJsonBackslashesTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="Тип 21", max_points=2, is_extended_answer=True)
        topic = Topic.objects.create(subject=self.subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        self.student = User.objects.create_user(username="st1", email="st1@example.com", password="pass", role="student")

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        self.submission = Submission.objects.create(student=self.student, task=self.task, image_url=image)

        model_obj = OpenRouterModel.objects.create(code="m1", label="M1", capabilities="vision")
        SubjectAIConfig.objects.create(subject=self.subject, photo_analysis_model=model_obj)

    def test_repairs_invalid_escape_in_json_string(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        # Модель вернула JSON, но положила LaTeX-команду с одинарным backslash внутри строки.
        # В JSON это интерпретируется как escape (\f, \t, \n, ...), что портит текст.
        bad = '{"primary_score": 1, "is_correct": false, "feedback": "Формула: \\\\frac{1}{2}"}'
        bad = bad.replace("\\\\frac", "\\frac")  # итоговая строка содержит `\frac` как в реальных ответах модели

        dummy = {"choices": [{"message": {"content": bad}}]}

        from unittest.mock import patch
        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy

            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.submission.id]))

        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["primary_score"], 1)
        # Должны восстановить правильный LaTeX с backslash
        self.assertIn("\\frac{1}{2}", payload["feedback"])
