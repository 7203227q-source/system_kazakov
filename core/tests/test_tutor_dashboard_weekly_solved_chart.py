import json
from datetime import datetime, time

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

<<<<<<< HEAD
from core.models import ExamFormat, StudentSubjectProfile, Subject, Submission, Task, TaskLog, TaskType, Topic, User
=======
from core.models import ExamFormat, StudentSubjectProfile, Subject, Submission, Task, TaskType, Topic, User
>>>>>>> trae/solo-agent-a9Fte2


class TutorDashboardWeeklySolvedChartTests(TestCase):
    def test_weekly_chart_counts_unique_tasks_per_day_by_last_attempt(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        StudentSubjectProfile.objects.create(student=student, subject=subj, exam_format=ef)

        topic = Topic.objects.create(subject=subj, name="T")
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1)
        task_a = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        task_b = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)

        today = timezone.localdate()
        d1 = today - timezone.timedelta(days=1)
        d2 = today - timezone.timedelta(days=2)

        s1 = Submission.objects.create(student=student, task=task_a, user_answer="0", is_correct=False, score=0)
<<<<<<< HEAD
        dt1 = timezone.make_aware(datetime.combine(d2, time(9, 0)))
        Submission.objects.filter(id=s1.id).update(created_at=dt1)
        l1 = TaskLog.objects.create(student=student, task=task_a, submission=s1, time_spent=120)
        TaskLog.objects.filter(id=l1.id).update(created_at=dt1)
        s2 = Submission.objects.create(student=student, task=task_a, user_answer="1", is_correct=True, score=1)
        dt2 = timezone.make_aware(datetime.combine(d2, time(21, 0)))
        Submission.objects.filter(id=s2.id).update(created_at=dt2)
        l2 = TaskLog.objects.create(student=student, task=task_a, submission=s2, time_spent=300)
        TaskLog.objects.filter(id=l2.id).update(created_at=dt2)

        s3 = Submission.objects.create(student=student, task=task_b, user_answer="0", is_correct=False, score=0)
        dt3 = timezone.make_aware(datetime.combine(d1, time(22, 0)))
        Submission.objects.filter(id=s3.id).update(created_at=dt3)
        l3 = TaskLog.objects.create(student=student, task=task_b, submission=s3, time_spent=240)
        TaskLog.objects.filter(id=l3.id).update(created_at=dt3)
=======
        Submission.objects.filter(id=s1.id).update(created_at=timezone.make_aware(datetime.combine(d2, time(9, 0))))
        s2 = Submission.objects.create(student=student, task=task_a, user_answer="1", is_correct=True, score=1)
        Submission.objects.filter(id=s2.id).update(created_at=timezone.make_aware(datetime.combine(d2, time(21, 0))))

        s3 = Submission.objects.create(student=student, task=task_b, user_answer="0", is_correct=False, score=0)
        Submission.objects.filter(id=s3.id).update(created_at=timezone.make_aware(datetime.combine(d1, time(22, 0))))
>>>>>>> trae/solo-agent-a9Fte2

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"), {"student_id": student.id, "subject_id": subj.id})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'id="studentWeeklySolvedChart"')

        raw = res.context.get("weekly_solved_chart_data")
        self.assertTrue(raw)
        data = json.loads(raw)

        labels = data["labels"]
        idx_d2 = next(i for i, x in enumerate(labels) if x.endswith(d2.strftime("%d.%m")))
        idx_d1 = next(i for i, x in enumerate(labels) if x.endswith(d1.strftime("%d.%m")))

        self.assertEqual(data["correct"][idx_d2], 1)
        self.assertEqual(data["incorrect"][idx_d2], 0)
        self.assertEqual(data["correct"][idx_d1], 0)
        self.assertEqual(data["incorrect"][idx_d1], 1)
<<<<<<< HEAD
        self.assertEqual(len(data["minutes"]), 7)
        self.assertEqual(int(data["minutes"][idx_d2]), 7)
        self.assertEqual(int(data["minutes"][idx_d1]), 4)
=======
>>>>>>> trae/solo-agent-a9Fte2

    def test_weekly_chart_counts_extended_score_on_scored_at_day(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subj = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        StudentSubjectProfile.objects.create(student=student, subject=subj, exam_format=ef)

        topic = Topic.objects.create(subject=subj, name="T")
        tt = TaskType.objects.create(exam_format=ef, number=30, name="30", max_points=3, is_extended_answer=True)
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="x", difficulty=10, exam_points=3)

        today = timezone.localdate()
        yesterday = today - timezone.timedelta(days=1)
        old_day = today - timezone.timedelta(days=10)
        tz = timezone.get_current_timezone()

        sub = Submission.objects.create(student=student, task=task, is_correct=None, score=2)
<<<<<<< HEAD
        scored_at = timezone.make_aware(datetime.combine(yesterday, time(18, 0)), tz)
        Submission.objects.filter(id=sub.id).update(
            created_at=timezone.make_aware(datetime.combine(old_day, time(10, 0)), tz),
            tutor_scored_at=scored_at,
        )
        log = TaskLog.objects.create(student=student, task=task, submission=sub, time_spent=420)
        TaskLog.objects.filter(id=log.id).update(created_at=scored_at)
=======
        Submission.objects.filter(id=sub.id).update(
            created_at=timezone.make_aware(datetime.combine(old_day, time(10, 0)), tz),
            tutor_scored_at=timezone.make_aware(datetime.combine(yesterday, time(18, 0)), tz),
        )
>>>>>>> trae/solo-agent-a9Fte2

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"), {"student_id": student.id, "subject_id": subj.id})
        self.assertEqual(res.status_code, 200)

        data = json.loads(res.context["weekly_solved_chart_data"])
        labels = data["labels"]
        idx = next(i for i, x in enumerate(labels) if x.endswith(yesterday.strftime("%d.%m")))
        self.assertEqual(int(data["correct"][idx]), 2)
        self.assertEqual(int(data["incorrect"][idx]), 1)
<<<<<<< HEAD
        self.assertEqual(len(data["minutes"]), 7)
        self.assertEqual(int(data["minutes"][idx]), 7)
=======
>>>>>>> trae/solo-agent-a9Fte2
