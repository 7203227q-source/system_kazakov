import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Assignment, ExamFormat, StudentSubjectProfile, Subject, Task, TaskType, Topic, User


class StudentDashboardDeadlineBadgesTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ", year=2026, is_active=True)
        StudentSubjectProfile.objects.create(student=self.student, subject=subj, exam_format=ef)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="Тип 1", max_points=1, is_extended_answer=False)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)

        today = timezone.now().date()
        self.a_soon = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="Soon",
            is_draft=False,
            is_deleted=False,
            is_completed=False,
            due_date=today + datetime.timedelta(days=2),
            exam_format=ef,
        )
        self.a_later = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="Later",
            is_draft=False,
            is_deleted=False,
            is_completed=False,
            due_date=today + datetime.timedelta(days=10),
            exam_format=ef,
        )
        self.a_none = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="NoDue",
            is_draft=False,
            is_deleted=False,
            is_completed=False,
            due_date=None,
            exam_format=ef,
        )
        for a in (self.a_soon, self.a_later, self.a_none):
            a.tasks.add(task)

    def test_dashboard_marks_due_soon_and_sorts(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_dashboard"))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")

        # До дедлайна осталось 2 дня -> должен появиться бейдж "Осталось: 2 дн" (красный/urgent).
        self.assertIn("Осталось: 2 дн", html)

        # Проверяем, что сортировка: ближайший due_date выше, а без due_date — внизу.
        pos_soon = html.find("Soon")
        pos_later = html.find("Later")
        pos_none = html.find("NoDue")
        self.assertTrue(0 <= pos_soon < pos_later < pos_none)
