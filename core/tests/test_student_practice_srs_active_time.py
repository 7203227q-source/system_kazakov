from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from core.models import (
    ExamFormat,
    SpacedRepetition,
    Subject,
    Task,
    TaskLog,
    TaskType,
    TaskVariant,
    Topic,
    User,
)


class StudentPracticeSrsActiveTimeTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="clock_s", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тест", max_points=1)
        topic = Topic.objects.create(subject=subject, name="T")
        self.task = Task.objects.create(
            topic=topic,
            task_type=task_type,
            correct_answer="7",
            difficulty=20,
            exam_points=1,
        )
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        SpacedRepetition.objects.create(
            student=self.student,
            task=self.task,
            next_review_date=timezone.localdate(),
        )

    def test_posted_active_time_is_saved_to_tasklog(self):
        self.client.force_login(self.student)
        self.client.get(reverse("student_practice") + "?mode=srs")
        token = self.client.session.get("practice_current", {}).get("token")

        res = self.client.post(
            reverse("student_practice"),
            {
                "task_id": self.task.id,
                "answer": "7",
                "mode": "srs",
                "attempt_token": token,
                "active_time_seconds": "97",
                "attempt_count": "1",
            },
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            TaskLog.objects.filter(student=self.student, task=self.task).latest("id").time_spent,
            97,
        )

    def test_invalid_active_time_falls_back_without_crashing(self):
        self.client.force_login(self.student)
        self.client.get(reverse("student_practice") + "?mode=srs")
        token = self.client.session.get("practice_current", {}).get("token")

        res = self.client.post(
            reverse("student_practice"),
            {
                "task_id": self.task.id,
                "answer": "0",
                "mode": "srs",
                "attempt_token": token,
                "active_time_seconds": "-25",
                "attempt_count": "3",
            },
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            TaskLog.objects.filter(student=self.student, task=self.task).latest("id").time_spent,
            60,
        )

    def test_practice_submit_srs_passes_default_review_context(self):
        self.client.force_login(self.student)

        with patch("core.views.process_task_submission") as process_task_submission:
            res = self.client.post(
                reverse("student_practice_submit", args=[self.task.id]),
                {
                    "answer": "7",
                    "mode": "srs",
                },
            )

        self.assertEqual(res.status_code, 302)
        process_task_submission.assert_called_once_with(
            self.student,
            self.task,
            5,
            active_time_seconds=60,
            attempt_count=1,
        )
