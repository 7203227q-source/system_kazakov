import json
from datetime import datetime, time

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, StudentSubjectProfile, Subject, Submission, Task, TaskType, Topic, User


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
        Submission.objects.filter(id=s1.id).update(created_at=timezone.make_aware(datetime.combine(d2, time(9, 0))))
        s2 = Submission.objects.create(student=student, task=task_a, user_answer="1", is_correct=True, score=1)
        Submission.objects.filter(id=s2.id).update(created_at=timezone.make_aware(datetime.combine(d2, time(21, 0))))

        s3 = Submission.objects.create(student=student, task=task_b, user_answer="0", is_correct=False, score=0)
        Submission.objects.filter(id=s3.id).update(created_at=timezone.make_aware(datetime.combine(d1, time(22, 0))))

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"), {"student_id": student.id, "subject_id": subj.id})
        self.assertEqual(res.status_code, 200)

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

