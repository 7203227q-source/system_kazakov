from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class PracticeAnswerLockTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="Тест", max_points=1)
        topic = Topic.objects.create(subject=subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="2", difficulty=50, exam_points=1)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>U</p>", solution="<p>S</p>")

    def test_second_submit_with_same_token_does_not_change_result(self):
        self.client.login(username="s", password="pass")

        # Simulate that the student is answering a currently shown task
        token = "tok1"
        session = self.client.session
        session["practice_current"] = {"token": token, "task_id": self.task.id, "mode": ""}
        session["practice_results"] = {}
        session.save()

        url = reverse("student_practice")
        res1 = self.client.post(
            url,
            {
                "task_id": self.task.id,
                "answer": "1",
                "attempt_token": token,
                "active_time_seconds": "44",
                "attempt_count": "1",
            },
        )
        self.assertEqual(res1.status_code, 200)
        self.assertContains(res1, "Неправильно")
        self.assertEqual(Submission.objects.filter(student=self.student, task=self.task).count(), 1)

        # Second submit (should be ignored/locked and return the same result)
        res2 = self.client.post(
            url,
            {
                "task_id": self.task.id,
                "answer": "2",
                "attempt_token": token,
                "active_time_seconds": "48",
                "attempt_count": "2",
            },
        )
        self.assertEqual(res2.status_code, 200)
        self.assertContains(res2, "Неправильно")
        self.assertEqual(Submission.objects.filter(student=self.student, task=self.task).count(), 1)

    def test_srs_second_submit_with_same_token_does_not_change_result(self):
        self.client.login(username="s", password="pass")

        token = "tok2"
        session = self.client.session
        session["practice_current"] = {"token": token, "task_id": self.task.id, "mode": "srs"}
        session["practice_results"] = {}
        session.save()

        url = reverse("student_practice")
        res1 = self.client.post(
            url,
            {
                "task_id": self.task.id,
                "answer": "1",
                "attempt_token": token,
                "mode": "srs",
                "active_time_seconds": "44",
                "attempt_count": "1",
            },
        )
        self.assertEqual(res1.status_code, 200)
        self.assertContains(res1, "Неправильно")
        self.assertEqual(Submission.objects.filter(student=self.student, task=self.task).count(), 1)

        res2 = self.client.post(
            url,
            {
                "task_id": self.task.id,
                "answer": "2",
                "attempt_token": token,
                "mode": "srs",
                "active_time_seconds": "48",
                "attempt_count": "2",
            },
        )
        self.assertEqual(res2.status_code, 200)
        self.assertContains(res2, "Неправильно")
        self.assertEqual(Submission.objects.filter(student=self.student, task=self.task).count(), 1)
