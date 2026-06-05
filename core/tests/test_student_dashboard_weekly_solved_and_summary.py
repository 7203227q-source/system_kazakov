import json
from datetime import datetime, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, StudentSubjectProfile, Subject, Submission, Task, TaskType, Topic, User


class StudentDashboardWeeklySolvedAndSummaryTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pw", role="student")
        self.client.force_login(self.student)

        self.subject = Subject.objects.create(name="Физика")
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")
        self.ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ физика", year=2026, is_active=True)
        self.tt = TaskType.objects.create(
            exam_format=self.ef,
            number=1,
            name="№1",
            max_points=1,
            is_extended_answer=False,
        )
        StudentSubjectProfile.objects.create(
            student=self.student,
            subject=self.subject,
            exam_format=self.ef,
            xp=0,
        )

        self.task = Task.objects.create(
            topic=self.topic,
            task_type=self.tt,
            correct_answer="1",
            exam_points=1,
        )

    def test_dashboard_provides_weekly_solved_chart_data_for_active_subject(self):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        tz = timezone.get_current_timezone()

        s1 = Submission.objects.create(
            student=self.student,
            task=self.task,
            is_correct=False,
        )
        Submission.objects.filter(id=s1.id).update(
            created_at=timezone.make_aware(datetime.combine(yesterday, time(10, 0)), tz),
        )
        s2 = Submission.objects.create(
            student=self.student,
            task=self.task,
            is_correct=True,
        )
        Submission.objects.filter(id=s2.id).update(
            created_at=timezone.make_aware(datetime.combine(yesterday, time(20, 0)), tz),
        )

        res = self.client.get(reverse("student_dashboard"), {"subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)

        raw = res.context.get("weekly_solved_chart_data")
        self.assertTrue(raw)
        data = json.loads(raw)

        self.assertEqual(len(data["labels"]), 7)
        self.assertEqual(len(data["correct"]), 7)
        self.assertEqual(len(data["incorrect"]), 7)

        idx = data["labels"].index(yesterday.strftime("%d %b"))
        self.assertEqual(int(data["correct"][idx]), 1)
        self.assertEqual(int(data["incorrect"][idx]), 0)

    def test_weekly_chart_uses_scoring_timestamp_for_extended_submissions(self):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        old_day = today - timedelta(days=10)
        tz = timezone.get_current_timezone()

        sub = Submission.objects.create(
            student=self.student,
            task=self.task,
            is_correct=True,
        )
        Submission.objects.filter(id=sub.id).update(
            created_at=timezone.make_aware(datetime.combine(old_day, time(10, 0)), tz),
            ai_last_verify_at=timezone.make_aware(datetime.combine(yesterday, time(20, 0)), tz),
        )

        res = self.client.get(reverse("student_dashboard"), {"subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)

        data = json.loads(res.context["weekly_solved_chart_data"])
        idx = data["labels"].index(yesterday.strftime("%d %b"))
        self.assertEqual(int(data["correct"][idx]), 1)
        self.assertEqual(int(data["incorrect"][idx]), 0)

    def test_dashboard_provides_submission_summary_for_active_subject(self):
        Submission.objects.create(student=self.student, task=self.task, is_correct=False)
        Submission.objects.create(student=self.student, task=self.task, is_correct=True)

        res = self.client.get(reverse("student_dashboard"), {"subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)

        self.assertEqual(int(res.context["student_total_submissions"]), 2)
        self.assertEqual(int(res.context["student_correct_rate"]), 50)
