from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Submission, Subject, Task, TaskType, Topic, User


class MobileUploadSecondPageTests(TestCase):
    def test_mobile_upload_page_has_second_input_and_capture(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        subj = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)
        sub = Submission.objects.create(student=student, task=task)
        token = sub.upload_token

        r = self.client.get(reverse("mobile_upload_draft", args=[token]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertIn('name="image"', html)
        self.assertIn('name="image2"', html)
        self.assertIn('capture="environment"', html)

    def test_status_returns_second_url(self):
        student = User.objects.create_user(username="s2", password="pass", role="student")
        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)
        img = SimpleUploadedFile("a.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
        sub = Submission.objects.create(student=student, task=task, image_url=img)

        self.client.force_login(student)
        r = self.client.get(reverse("api_submission_status", args=[sub.id]))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("image_url_2", data)
