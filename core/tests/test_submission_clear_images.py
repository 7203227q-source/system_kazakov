import base64

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User, Submission


class SubmissionClearImagesTests(TestCase):
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
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")
        self.task = Task.objects.create(
            fipi_id="X1",
            topic=self.topic,
            task_type=self.task_type,
            correct_answer="1",
            difficulty=10,
            exam_points=2,
        )
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        self.student = User.objects.create_user(username="st1", password="pw", role="student")
        self.other = User.objects.create_user(username="st2", password="pw", role="student")

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        image2 = SimpleUploadedFile("b.png", png_bytes, content_type="image/png")

        self.submission = Submission.objects.create(
            student=self.student,
            task=self.task,
            image_url=image,
            image_url_2=image2,
            ai_feedback="old",
            ai_recognized_solution="sol",
            ai_mistakes_json='["m"]',
            ai_verdict_json='["v"]',
            primary_score=1,
            is_correct=False,
        )

    def test_owner_can_clear_images_and_ai_fields(self):
        self.client.force_login(self.student)
        res = self.client.post(reverse("api_submission_clear_images", args=[self.submission.id]))
        self.assertEqual(res.status_code, 200)

        self.submission.refresh_from_db()
        self.assertFalse(bool(self.submission.image_url))
        self.assertFalse(bool(getattr(self.submission, "image_url_2", None)))
        self.assertIsNone(self.submission.ai_feedback)
        self.assertIsNone(self.submission.ai_recognized_solution)
        self.assertIsNone(self.submission.ai_mistakes_json)
        self.assertIsNone(self.submission.ai_verdict_json)
        self.assertEqual(self.submission.primary_score, 0)
        self.assertFalse(self.submission.is_correct)

    def test_other_student_forbidden(self):
        self.client.force_login(self.other)
        res = self.client.post(reverse("api_submission_clear_images", args=[self.submission.id]))
        self.assertEqual(res.status_code, 403)

