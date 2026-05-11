import datetime

from django.test import TestCase
from django.urls import reverse

from core.models import (
    Assignment,
    ExamFormat,
    Subject,
    Task,
    TaskType,
    TaskVariant,
    Topic,
    User,
    StudentSubjectProfile,
)


class SubjectStreakTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.subject = Subject.objects.create(name="Математика")
        self.profile = StudentSubjectProfile.objects.create(
            student=self.student,
            subject=self.subject,
            target_score=80,
            current_streak=0,
        )

    def test_first_touch_sets_streak_to_1(self):
        from core.analytics import touch_subject_streak

        today = datetime.date(2026, 5, 11)
        touch_subject_streak(self.student, self.subject, today=today)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.current_streak, 1)
        self.assertEqual(self.profile.last_streak_date, today)

    def test_second_day_increments(self):
        from core.analytics import touch_subject_streak

        d1 = datetime.date(2026, 5, 11)
        d2 = datetime.date(2026, 5, 12)
        touch_subject_streak(self.student, self.subject, today=d1)
        touch_subject_streak(self.student, self.subject, today=d2)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.current_streak, 2)
        self.assertEqual(self.profile.last_streak_date, d2)

    def test_same_day_is_idempotent(self):
        from core.analytics import touch_subject_streak

        d1 = datetime.date(2026, 5, 11)
        touch_subject_streak(self.student, self.subject, today=d1)
        touch_subject_streak(self.student, self.subject, today=d1)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.current_streak, 1)
        self.assertEqual(self.profile.last_streak_date, d1)

    def test_gap_resets_to_1(self):
        from core.analytics import touch_subject_streak

        d1 = datetime.date(2026, 5, 11)
        d3 = datetime.date(2026, 5, 13)
        touch_subject_streak(self.student, self.subject, today=d1)
        touch_subject_streak(self.student, self.subject, today=d3)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.current_streak, 1)
        self.assertEqual(self.profile.last_streak_date, d3)

    def test_assignment_check_touches_streak(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        tutor.students.add(self.student)

        ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ математика", year=2026, is_active=True)
        topic = Topic.objects.create(subject=self.subject, name="Задания")
        tt = TaskType.objects.create(exam_format=ef, number=1, name="Тип 1", max_points=1)
        task = Task.objects.create(
            topic=topic,
            task_type=tt,
            subtype_tag="x",
            correct_answer="1",
            difficulty=50,
            exam_points=1,
        )
        TaskVariant.objects.create(task=task, theme="classic", content="x", solution="y")
        a = Assignment.objects.create(tutor=tutor, student=self.student, title="A", is_draft=False)
        a.tasks.add(task)

        self.client.login(username="s", password="pass")
        res = self.client.post(reverse("student_check_assignment_task", args=[a.id, task.id]), {"answer": "0"})
        self.assertEqual(res.status_code, 200)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.current_streak, 1)

