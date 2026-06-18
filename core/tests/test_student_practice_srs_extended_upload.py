import base64

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch
import json

from core.models import ExamFormat, OpenRouterModel, SpacedRepetition, Subject, SubjectAIConfig, Submission, Task, TaskType, TaskVariant, Topic, User


class StudentPracticeSrsExtendedUploadTests(TestCase):
    def test_srs_extended_task_shows_upload_controls(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        subj = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        SpacedRepetition.objects.create(student=student, task=task, next_review_date=timezone.now().date())

        # AI config нужна, чтобы кнопка проверки имела смысл (но UI должен быть и без неё)
        m = OpenRouterModel.objects.create(code="m1", label="M1", capabilities="vision", is_active=True)
        SubjectAIConfig.objects.create(subject=subj, photo_analysis_model=m)

        self.client.force_login(student)
        r = self.client.get(reverse("student_practice") + "?mode=srs")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertIn("Загрузите решение", html)
        self.assertIn("Проверить решение через ИИ", html)
        self.assertIn('id="srs_camera_1"', html)
        self.assertIn('id="srs_gallery_1"', html)
        self.assertIn('id="srs_camera_2"', html)
        self.assertIn('id="srs_gallery_2"', html)
        self.assertIn('capture="environment"', html)
        # Место для вывода вердикта ИИ после проверки
        self.assertIn("id=\"srs_ai_verdict\"", html)

    def test_srs_extended_task_does_not_show_previous_solution_photos(self):
        student = User.objects.create_user(username="s2", password="pass", role="student")
        subj = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        SpacedRepetition.objects.create(student=student, task=task, next_review_date=timezone.now().date())

        img = SimpleUploadedFile("a.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
        Submission.objects.create(student=student, task=task, image_url=img)

        self.client.force_login(student)
        r = self.client.get(reverse("student_practice") + "?mode=srs")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertIn("Загрузите решение", html)
        self.assertNotIn("Решение загружено", html)
        self.assertIn('id="srs_camera_2"', html)
        self.assertIn('id="srs_gallery_2"', html)

    def test_srs_extended_task_keeps_uploaded_photos_on_refresh_in_same_attempt(self):
        student = User.objects.create_user(username="s3", password="pass", role="student")
        subj = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        SpacedRepetition.objects.create(student=student, task=task, next_review_date=timezone.now().date())

        self.client.force_login(student)
        r1 = self.client.get(reverse("student_practice") + "?mode=srs")
        self.assertEqual(r1.status_code, 200)
        submission = r1.context.get("practice_submission")
        self.assertIsNotNone(submission)

        img = SimpleUploadedFile("a.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
        upload_resp = self.client.post(
            reverse("api_submission_upload", args=[submission.id]),
            data={"image": img},
        )
        self.assertEqual(upload_resp.status_code, 200)

        r2 = self.client.get(reverse("student_practice") + "?mode=srs")
        self.assertEqual(r2.status_code, 200)
        html2 = r2.content.decode("utf-8")
        self.assertIn("Решение загружено", html2)

    def test_srs_ai_verify_returns_updated_remaining_counter(self):
        student = User.objects.create_user(username="s4", password="pass", role="student")
        subj = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        SpacedRepetition.objects.create(student=student, task=task, next_review_date=timezone.now().date())

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        submission = Submission.objects.create(student=student, task=task, image_url=image)

        m = OpenRouterModel.objects.create(code="m1", label="M1", capabilities="vision", is_active=True)
        SubjectAIConfig.objects.create(subject=subj, photo_analysis_model=m)

        recognition = {
            "photo_valid": True,
            "photo_valid_reason": "",
            "recognition_confidence": 0.9,
            "recognized_solution": "x=1",
        }
        grading = {"primary_score": 3, "is_correct": True, "feedback": "ok"}
        dummy_response_1 = {"choices": [{"message": {"content": json.dumps(recognition, ensure_ascii=False)}}]}
        dummy_response_2 = {"choices": [{"message": {"content": json.dumps(grading, ensure_ascii=False)}}]}

        class R:
            def __init__(self, payload):
                self.status_code = 200
                self._payload = payload

            def json(self):
                return self._payload

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test"}, clear=False):
            with patch("core.views.requests.post") as post:
                post.side_effect = [R(dummy_response_1), R(dummy_response_2)]
                self.client.force_login(student)
                res = self.client.post(reverse("api_verify_with_ai", args=[submission.id]))

        self.assertEqual(res.status_code, 200, res.content)
        payload = res.json()
        self.assertEqual(payload["srs_due_remaining"], 0)
