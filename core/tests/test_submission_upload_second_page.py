import base64

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class SubmissionUploadSecondPageTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="Тип 21", max_points=2, is_extended_answer=True)
        topic = Topic.objects.create(subject=self.subject, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        self.student = User.objects.create_user(username="st1", email="st1@example.com", password="pass", role="student")
        self.submission = Submission.objects.create(student=self.student, task=task)

    def test_upload_can_set_second_page(self):
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image1 = SimpleUploadedFile("a1.png", png_bytes, content_type="image/png")
        image2 = SimpleUploadedFile("a2.png", png_bytes, content_type="image/png")

        self.client.force_login(self.student)
        url = reverse("api_submission_upload", args=[self.submission.id])
        res = self.client.post(url, data={"image": image1, "image2": image2})
        self.assertEqual(res.status_code, 200, res.content)

        self.submission.refresh_from_db()
        self.assertTrue(bool(self.submission.image_url))
        self.assertTrue(bool(self.submission.image_url_2))

