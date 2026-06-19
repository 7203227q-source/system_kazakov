from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.dashboard_analytics import build_task_type_rates
from core.models import ExamFormat, StudentSubjectProfile, Subject, Submission, Task, TaskType, Topic, User


class TaskTypeRateRetrospectiveTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pw", role="student")
        self.subject = Subject.objects.create(name="Физика")
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")
        self.exam_format = ExamFormat.objects.create(
            subject=self.subject,
            name="ОГЭ физика",
            year=2026,
            is_active=True,
        )
        StudentSubjectProfile.objects.create(
            student=self.student,
            subject=self.subject,
            exam_format=self.exam_format,
            xp=0,
        )
        self.task_type = TaskType.objects.create(
            exam_format=self.exam_format,
            number=1,
            name="№1",
            max_points=1,
            is_extended_answer=False,
        )
        self.task = Task.objects.create(
            topic=self.topic,
            task_type=self.task_type,
            correct_answer="1",
            exam_points=1,
        )

    def test_snapshot_uses_state_known_on_anchor_day(self):
        today = timezone.localdate()
        older_dt = timezone.now() - timedelta(days=20)
        newer_dt = timezone.now() - timedelta(days=2)

        s1 = Submission.objects.create(student=self.student, task=self.task, is_correct=False, score=0)
        Submission.objects.filter(id=s1.id).update(created_at=older_dt)

        s2 = Submission.objects.create(student=self.student, task=self.task, is_correct=True, score=1)
        Submission.objects.filter(id=s2.id).update(created_at=newer_dt)

        rates, _ = build_task_type_rates(
            self.student,
            subject_id=self.subject.id,
            exam_format=self.exam_format,
            today=today,
        )

        tile = next(item for item in rates if int(item["number"]) == 1)
        retrospective = {int(point["days_ago"]): point["rate"] for point in tile["retrospective"]}

        self.assertEqual(int(round(float(retrospective[4]))), 0)
        self.assertEqual(int(round(float(tile["rate"]))), 100)

    def test_snapshot_uses_last_attempt_known_by_that_day(self):
        today = timezone.localdate()
        old_dt = timezone.now() - timedelta(days=40)
        mid_dt = timezone.now() - timedelta(days=10)

        s1 = Submission.objects.create(student=self.student, task=self.task, is_correct=True, score=1)
        Submission.objects.filter(id=s1.id).update(created_at=old_dt)

        s2 = Submission.objects.create(student=self.student, task=self.task, is_correct=False, score=0)
        Submission.objects.filter(id=s2.id).update(created_at=mid_dt)

        rates, _ = build_task_type_rates(
            self.student,
            subject_id=self.subject.id,
            exam_format=self.exam_format,
            today=today,
        )

        tile = next(item for item in rates if int(item["number"]) == 1)
        retrospective = {int(point["days_ago"]): point["rate"] for point in tile["retrospective"]}

        self.assertEqual(int(round(float(retrospective[32]))), 100)
        self.assertEqual(int(round(float(retrospective[8]))), 0)
