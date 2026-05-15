from django.test import TestCase
from django.urls import reverse

from core.models import Subject, ExamFormat, TaskType, Topic, Task, TaskTag, User


class TutorTaskBankAIFieldsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="a", password="pw", role="admin")
        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        self.task_type = TaskType.objects.create(exam_format=self.exam_format, number=1, name="Тип 1", max_points=1)
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")

        self.t1 = Task.objects.create(
            topic=self.topic,
            task_type=self.task_type,
            correct_answer="1",
            ai_difficulty_raw=10,
            ai_difficulty_exam_percentile=5,
            ai_difficulty_type_percentile=7,
        )
        self.t2 = Task.objects.create(
            topic=self.topic,
            task_type=self.task_type,
            correct_answer="1",
            ai_difficulty_raw=80,
            ai_difficulty_exam_percentile=90,
            ai_difficulty_type_percentile=95,
        )
        tag = TaskTag.objects.create(kind="method", name="логарифмы")
        self.t2.ai_tags.add(tag)

    def test_renders_ai_fields(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("tutor_task_bank"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "AI сложность")
        self.assertContains(res, "10/100")
        self.assertContains(res, "80/100")
        self.assertContains(res, "логарифмы")

    def test_filters_by_ai_raw_min(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("tutor_task_bank"), {"ai_raw_min": "50"})
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, "10/100")
        self.assertContains(res, "80/100")

    def test_filters_by_tag_query(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("tutor_task_bank"), {"tag_q": "логар"})
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, "10/100")
        self.assertContains(res, "логарифмы")
