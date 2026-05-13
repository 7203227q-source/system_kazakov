from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Submission, Subject, Task, TaskType, Topic, User


class AIVerifySecondPartOnlyTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ математика", year=2026, is_active=True)
        tt1 = TaskType.objects.create(exam_format=ef, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subj, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt1, correct_answer="1", difficulty=10, exam_points=1)

        self.sub = Submission.objects.create(student=self.student, task=self.task, is_correct=None)
        self.sub.image_url = SimpleUploadedFile("a.jpg", b"fake", content_type="image/jpeg")
        self.sub.save()

    def test_verify_rejected_for_test_part(self):
        self.client.login(username="s", password="pass")
        res = self.client.post(reverse("api_verify_with_ai", args=[self.sub.id]))
        self.assertEqual(res.status_code, 400)
        self.sub.refresh_from_db()
        self.assertIsNone(self.sub.primary_score)
        self.assertIsNone(self.sub.is_correct)
        self.assertIsNone(self.sub.ai_feedback)

    def test_verify_requires_openrouter_config(self):
        tt2 = TaskType.objects.create(exam_format=self.task.task_type.exam_format, number=20, name="Тип 20", max_points=2)
        t2 = Task.objects.create(topic=self.task.topic, task_type=tt2, correct_answer="1", difficulty=10, exam_points=2)
        sub2 = Submission.objects.create(student=self.student, task=t2, is_correct=None)
        sub2.image_url = SimpleUploadedFile("b.jpg", b"fake", content_type="image/jpeg")
        sub2.save()

        self.client.login(username="s", password="pass")
        res = self.client.post(reverse("api_verify_with_ai", args=[sub2.id]))
        self.assertEqual(res.status_code, 400)
        sub2.refresh_from_db()
        self.assertIsNone(sub2.primary_score)
        self.assertIsNone(sub2.is_correct)
        self.assertIsNone(sub2.ai_feedback)
