from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class TutorTodayXpTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="Тест", max_points=1)
        topic = Topic.objects.create(subject=subject, name="T")
        self.task1 = Task.objects.create(topic=topic, task_type=tt, correct_answer="2", difficulty=50, exam_points=1)
        self.task2 = Task.objects.create(topic=topic, task_type=tt, correct_answer="3", difficulty=20, exam_points=1)
        TaskVariant.objects.create(task=self.task1, theme="classic", content="<p>U</p>", solution="<p>S</p>")
        TaskVariant.objects.create(task=self.task2, theme="classic", content="<p>U</p>", solution="<p>S</p>")

    def test_tutor_sees_today_xp_in_student_card(self):
        now = timezone.now()
        yesterday = now - timezone.timedelta(days=1)

        s1 = Submission.objects.create(student=self.student, task=self.task1, user_answer="2", is_correct=True, score=1)
        Submission.objects.filter(id=s1.id).update(created_at=now)
        s2 = Submission.objects.create(student=self.student, task=self.task2, user_answer="3", is_correct=True, score=1)
        Submission.objects.filter(id=s2.id).update(created_at=yesterday)

        # task1 difficulty=50 => 10 XP, task2 yesterday => ignored
        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Сегодня")
        self.assertContains(res, "+10 XP")

    def test_tutor_student_list_shows_real_forecast_not_hardcoded(self):
        from core.models import DailySnapshot

        # create a snapshot so forecast is real and deterministic
        DailySnapshot.objects.create(student=self.student, subject=self.task1.topic.subject, predicted_exam_score=72.0, current_mastery=45.0)

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Прогноз: 72")
