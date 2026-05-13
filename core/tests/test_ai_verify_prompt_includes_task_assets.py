import json
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, OpenRouterModel, Subject, SubjectAIConfig, Submission, Task, TaskType, TaskVariant, Topic, User


class AIVerifyPromptIncludesTaskAssetsTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=20, name="Тип 20", max_points=2, is_extended_answer=True)
        topic = Topic.objects.create(subject=self.subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)
        TaskVariant.objects.create(
            task=self.task,
            theme="classic",
            content="<p>Условие: формула \\frac{1}{2} и построй график</p><img src=\"/media/a.png\"><img src=\"https://math-ege.sdamgia.ru/img/b.png\"><img src=\"data:image/png;base64,AAA\"><img src=\"https://evil.com/x.png\">",
            solution="",
        )

        self.sub = Submission.objects.create(student=self.student, task=self.task, is_correct=None)
        self.sub.image_url = SimpleUploadedFile("a.jpg", b"fake", content_type="image/jpeg")
        self.sub.save()

        self.m = OpenRouterModel.objects.create(code="m1", label="M1", capabilities="vision", is_active=True)
        SubjectAIConfig.objects.create(subject=self.subject, photo_analysis_model=self.m)

    def test_prompt_text_and_images_are_attached(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        dummy = {"choices": [{"message": {"content": json.dumps({"primary_score": 1, "is_correct": False, "feedback": "ok"})}}]}

        from unittest.mock import patch
        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy

            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.sub.id]))

        self.assertEqual(res.status_code, 200)
        sent_payload = post.call_args.kwargs["json"]
        user_msg = next(m for m in sent_payload["messages"] if m["role"] == "user")
        content = user_msg["content"]
        text = next(p["text"] for p in content if p["type"] == "text")
        self.assertIn("Условие:", text)
        # Экранируем обратные слэши в тексте, чтобы у провайдеров не ломался JSON
        self.assertIn("\\\\frac{1}{2}", text)

        imgs = [p["image_url"]["url"] for p in content if p["type"] == "image_url"]
        self.assertTrue(any("/media/a.png" in u for u in imgs))
        # В OpenRouter отправляем только локальные картинки (/media/), чтобы провайдер не падал на внешних URL
        self.assertFalse(any("math-ege.sdamgia.ru" in u for u in imgs))
        self.assertFalse(any("evil.com" in u for u in imgs))
        self.assertTrue(any(u.startswith("data:") for u in imgs))
        task_imgs = [u for u in imgs if not u.startswith("data:")]
        self.assertFalse(any(u.startswith("data:") for u in task_imgs))
