import base64
import json
import os
import os.path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.conf import settings

from core.models import ExamFormat, OpenRouterModel, Subject, SubjectAIConfig, Submission, Task, TaskType, TaskVariant, Topic, User


class SubmissionVerifyOpenRouterTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        self.task_type = TaskType.objects.create(exam_format=self.exam_format, number=20, name="Тип 20", max_points=2, is_extended_answer=True)
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

        sent_payload = post.call_args.kwargs["json"]
        self.assertNotIn("response_format", sent_payload)
        user_msg = next(m for m in sent_payload["messages"] if m["role"] == "user")
        prompt_text = next(p["text"] for p in user_msg["content"] if p["type"] == "text")
        self.assertIn("0 до", prompt_text)
        self.assertIn("сняты", prompt_text)
        self.assertIn("$...$", prompt_text)
        self.assertIn("$$...$$", prompt_text)

        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["primary_score"], 1)
        self.assertTrue(payload["is_correct"])
        self.assertEqual(payload["model"], "google/gemini-2.0-flash")

    def test_verify_repairs_invalid_json_backslashes_in_feedback(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        content = '{"primary_score": 1, "is_correct": true, "feedback": "$\\pi$"}'
        dummy_response = {"choices": [{"message": {"content": content}}]}

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
        self.assertIn("\\pi", payload["feedback"])

    def test_verify_repairs_invalid_json_u_escape_in_feedback(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        content = '{"primary_score": 1, "is_correct": true, "feedback": "$\\underline{x}$"}'
        dummy_response = {"choices": [{"message": {"content": content}}]}

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
        self.assertIn("\\underline", payload["feedback"])

    def test_verify_inlines_task_media_images_as_data_urls(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        tasks_dir = os.path.join(settings.MEDIA_ROOT, "tasks")
        os.makedirs(tasks_dir, exist_ok=True)
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        with open(os.path.join(tasks_dir, "t.png"), "wb") as f:
            f.write(png_bytes)

        v = self.task.variants.filter(theme="classic").first()
        v.content = '<p>Q</p><img src="/media/tasks/t.png">'
        v.save(update_fields=["content"])

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

        sent_payload = post.call_args.kwargs["json"]
        user_msg = next(m for m in sent_payload["messages"] if m["role"] == "user")
        urls = [p["image_url"]["url"] for p in user_msg["content"] if p["type"] == "image_url"]
        self.assertTrue(any(u.startswith("data:image/png;base64,") for u in urls))
        self.assertFalse(any("/media/tasks/t.png" in u for u in urls))

    def test_verify_skips_svg_task_images(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        tasks_dir = os.path.join(settings.MEDIA_ROOT, "tasks")
        os.makedirs(tasks_dir, exist_ok=True)
        with open(os.path.join(tasks_dir, "t.svg"), "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>')

        v = self.task.variants.filter(theme="classic").first()
        v.content = '<p>Q</p><img src="/media/tasks/t.svg">'
        v.save(update_fields=["content"])

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

        sent_payload = post.call_args.kwargs["json"]
        user_msg = next(m for m in sent_payload["messages"] if m["role"] == "user")
        urls = [p["image_url"]["url"] for p in user_msg["content"] if p["type"] == "image_url"]
        self.assertFalse(any("t.svg" in u for u in urls))
