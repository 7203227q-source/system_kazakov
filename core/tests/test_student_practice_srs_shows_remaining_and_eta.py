from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, Subject, Task, TaskLog, TaskType, TaskVariant, Topic, User


class StudentPracticeSrsShowsRemainingAndEtaTests(TestCase):
    def test_srs_shows_remaining_and_eta(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1, is_extended_answer=False)
        topic = Topic.objects.create(subject=subj, name="T")

        tasks = []
        for _ in range(3):
            t = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
            TaskVariant.objects.create(task=t, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
            SpacedRepetition.objects.create(student=student, task=t, next_review_date=timezone.now().date())
            tasks.append(t)

        TaskLog.objects.create(student=student, task=tasks[0], time_spent=60, score=1.0, is_anomaly=False)

        self.client.force_login(student)
        r = self.client.get(reverse("student_practice") + "?mode=srs")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertIn("Сегодня повторить", html)
        self.assertIn("≈", html)

