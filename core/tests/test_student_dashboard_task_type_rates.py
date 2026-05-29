from datetime import datetime, time

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, StudentSubjectProfile, Subject, Submission, Task, TaskType, Topic, User


class StudentDashboardTaskTypeRatesTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pw", role="student")
        self.client.force_login(self.student)

        self.subject = Subject.objects.create(name="Физика")
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")
        self.ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ физика", year=2026, is_active=True)

        self.tt1 = TaskType.objects.create(
            exam_format=self.ef,
            number=1,
            name="№1",
            max_points=1,
            is_extended_answer=False,
        )
        self.tt2 = TaskType.objects.create(
            exam_format=self.ef,
            number=2,
            name="№2",
            max_points=2,
            is_extended_answer=False,
        )

        StudentSubjectProfile.objects.create(student=self.student, subject=self.subject, exam_format=self.ef, xp=0)

        self.t1 = Task.objects.create(topic=self.topic, task_type=self.tt1, correct_answer="1", exam_points=1)
        self.t2 = Task.objects.create(topic=self.topic, task_type=self.tt2, correct_answer="12", exam_points=0)

    def test_dashboard_includes_task_type_rates_for_active_subject_and_exam_format(self):
        tz = timezone.get_current_timezone()
        created_at = timezone.make_aware(datetime.combine(timezone.localdate(), time(12, 0)), tz)

        s1 = Submission.objects.create(student=self.student, task=self.t1, is_correct=True)
        Submission.objects.filter(id=s1.id).update(created_at=created_at)

        s2 = Submission.objects.create(student=self.student, task=self.t2, is_correct=False, score=1)
        Submission.objects.filter(id=s2.id).update(created_at=created_at)

        res = self.client.get(reverse("student_dashboard"), {"subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)

        rates = res.context.get("task_type_rates")
        self.assertTrue(isinstance(rates, list))
        self.assertEqual([r["number"] for r in rates], [1, 2])

        r1 = next(r for r in rates if r["number"] == 1)
        self.assertEqual(int(r1["total"]), 1)
        self.assertEqual(int(r1["correct"]), 1)
        self.assertEqual(int(round(float(r1["rate"]))), 100)

        r2 = next(r for r in rates if r["number"] == 2)
        self.assertEqual(int(r2["total"]), 2)
        self.assertEqual(int(r2["correct"]), 1)
        self.assertEqual(int(round(float(r2["rate"]))), 50)

    def test_dashboard_shows_no_tiles_when_exam_format_not_selected(self):
        StudentSubjectProfile.objects.filter(student=self.student, subject=self.subject).update(exam_format=None)
        res = self.client.get(reverse("student_dashboard"), {"subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context.get("task_type_rates"), [])
        self.assertIsNone(res.context.get("active_exam_format_label"))

