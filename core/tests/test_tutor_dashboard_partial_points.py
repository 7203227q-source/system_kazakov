import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    DailySnapshot,
    ExamFormat,
    StudentSubjectProfile,
    Subject,
    Submission,
    Task,
    TaskType,
    Topic,
    User,
)


class TutorDashboardPartialPointsTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        self.subject = Subject.objects.create(name="Физика")
        self.ef = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        self.tt = TaskType.objects.create(exam_format=self.ef, number=1, name="N1", max_points=3)

        topic = Topic.objects.create(subject=self.subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=self.tt, correct_answer="x", difficulty=50, exam_points=3)

        StudentSubjectProfile.objects.create(student=self.student, subject=self.subject, exam_format=self.ef)
        DailySnapshot.objects.create(student=self.student, subject=self.subject, date=timezone.localdate())

    def test_partial_points_affect_tiles_weekly_and_accuracy(self):
        now = timezone.now()

        sub = Submission.objects.create(
            student=self.student,
            task=self.task,
            is_correct=False,
            tutor_primary_score=1,
        )
        Submission.objects.filter(id=sub.id).update(created_at=now)

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"), {"student_id": self.student.id, "subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)

        tiles = list(res.context["task_type_rates"])
        tile = next(t for t in tiles if int(t["number"]) == 1)

        self.assertEqual(int(tile["total"]), 3)
        self.assertEqual(int(tile["correct"]), 1)
        self.assertEqual(int(round(float(tile["rate"] or 0.0))), 33)

        self.assertEqual(int(round(float(res.context["student_correct_rate"] or 0.0))), 33)

        weekly = json.loads(res.context["weekly_solved_chart_data"])
        self.assertEqual(int(weekly["correct"][-1]), 1)
        self.assertEqual(int(weekly["incorrect"][-1]), 2)

