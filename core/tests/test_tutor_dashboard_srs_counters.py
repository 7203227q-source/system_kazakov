from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, Subject, Task, TaskType, Topic, User
from core.services import process_srs_review


class TutorDashboardSrsCountersTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="Тест", max_points=1)
        topic = Topic.objects.create(subject=subject, name="T")
        self.task1 = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        self.task2 = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)

    def test_process_srs_review_sets_last_reviewed_at(self):
        rec = SpacedRepetition.objects.create(
            student=self.student,
            task=self.task1,
            next_review_date=timezone.localdate(),
        )
        self.assertIsNone(getattr(rec, "last_reviewed_at", None))

        before = timezone.now()
        process_srs_review(rec, grade=5)
        rec.refresh_from_db()
        self.assertIsNotNone(rec.last_reviewed_at)
        self.assertGreaterEqual(rec.last_reviewed_at, before)

    def test_tutor_dashboard_shows_srs_due_and_reviewed_today(self):
        today = timezone.localdate()
        yesterday = today - timezone.timedelta(days=1)

        SpacedRepetition.objects.create(student=self.student, task=self.task1, next_review_date=today)
        SpacedRepetition.objects.create(student=self.student, task=self.task2, next_review_date=yesterday)

        SpacedRepetition.objects.filter(student=self.student, task=self.task2).update(last_reviewed_at=timezone.now())

        self.client.login(username="t", password="pass")
        r = self.client.get(reverse("tutor_dashboard"))
        self.assertEqual(r.status_code, 200)

        self.assertContains(r, "Повтор сегодня")
        self.assertContains(r, "Повторил")
        self.assertContains(r, "Повтор сегодня: 2")
        self.assertContains(r, "Повторил: 1")
