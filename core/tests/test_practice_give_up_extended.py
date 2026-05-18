from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, Subject, Submission, Task, TaskLog, TaskType, TaskVariant, Topic, User


class PracticeGiveUpExtendedTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=20, name="2-я часть", max_points=2, is_extended_answer=True)
        topic = Topic.objects.create(subject=subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="", difficulty=50, exam_points=2)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>U</p>", solution="<p>S</p>")

    def test_give_up_extended_in_adaptive_mode_renders_solution(self):
        self.client.login(username="s", password="pass")

        token = "tok_giveup_1"
        session = self.client.session
        session["practice_current"] = {"token": token, "task_id": self.task.id, "mode": ""}
        session["practice_results"] = {}
        session.save()

        url = reverse("student_practice")
        res = self.client.post(url, {"task_id": self.task.id, "attempt_token": token, "give_up": "1"})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Неправильно")
        self.assertContains(res, "Не могу решить")
        self.assertContains(res, "Показать подробное решение")
        self.assertEqual(Submission.objects.filter(student=self.student, task=self.task, is_correct=False).count(), 1)
        self.assertEqual(TaskLog.objects.filter(student=self.student, task=self.task).count(), 1)

    def test_give_up_extended_in_srs_mode_updates_next_review_date(self):
        self.client.login(username="s", password="pass")

        SpacedRepetition.objects.create(student=self.student, task=self.task, next_review_date=timezone.now().date())

        token = "tok_giveup_2"
        session = self.client.session
        session["practice_current"] = {"token": token, "task_id": self.task.id, "mode": "srs"}
        session["practice_results"] = {}
        session.save()

        url = reverse("student_practice")
        res = self.client.post(url, {"task_id": self.task.id, "attempt_token": token, "give_up": "1", "mode": "srs"})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Неправильно")
        self.assertContains(res, "?mode=srs")

        rec = SpacedRepetition.objects.get(student=self.student, task=self.task)
        self.assertGreater(rec.next_review_date, timezone.now().date())

