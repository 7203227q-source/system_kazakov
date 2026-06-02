import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Assignment,
    DailySnapshot,
    ExamFormat,
    ExamScoreScale,
    StudentSubjectProfile,
    Subject,
    Task,
    TaskType,
    Topic,
    Submission,
    User,
)


class LearningVelocityCalibrationTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ОГЭ", year=2026, is_active=True)
        self.scale = ExamScoreScale.objects.create(exam_format=self.exam_format, max_primary_score=10, grade_rules=[])

        self.profile = StudentSubjectProfile.objects.create(
            student=self.student,
            subject=self.subject,
            exam_format=self.exam_format,
            learning_velocity=1.0,
        )

        topic = Topic.objects.create(subject=self.subject, name="T")
        self.tt = TaskType.objects.create(
            exam_format=self.exam_format,
            number=1,
            name="Тип 1",
            max_points=2,
            is_extended_answer=False,
        )
        self.tasks = [
            Task.objects.create(topic=topic, task_type=self.tt, correct_answer="1", difficulty=10, exam_points=2)
            for _ in range(5)
        ]

        DailySnapshot.objects.create(
            student=self.student,
            subject=self.subject,
            date=timezone.now().date() - datetime.timedelta(days=1),
            current_mastery=50.0,
            predicted_exam_score=50.0,
        )

    def _make_assignment_with_full_score(self, *, due_date):
        a = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="A",
            is_draft=False,
            is_deleted=False,
            is_completed=False,
            is_verified=True,
            due_date=due_date,
            exam_format=self.exam_format,
        )
        a.tasks.add(*self.tasks)
        return a

    def test_learning_velocity_calibrates_on_finish_assignment_with_warmup(self):
        a = self._make_assignment_with_full_score(due_date=timezone.now().date())
        self.client.login(username="s", password="pass")

        payload = {"action": "finish"}
        for t in self.tasks:
            payload[f"answer_{t.id}"] = "1"

        res = self.client.post(reverse("student_solve_assignment", args=[a.id]), data=payload, follow=False)
        self.assertIn(res.status_code, (302, 303))

        self.profile.refresh_from_db()
        # err=+50, k=0.15 => 0.075, clamp => 0.06, warmup(0) => *0.3 => 0.018
        self.assertAlmostEqual(float(self.profile.learning_velocity), 1.018, places=3)

        a.refresh_from_db()
        self.assertIsNotNone(getattr(a, "learning_velocity_calibrated_at", None))

    def test_learning_velocity_penalizes_late_assignments(self):
        yesterday = timezone.now().date() - datetime.timedelta(days=1)
        a = self._make_assignment_with_full_score(due_date=yesterday)

        # Имитируем сценарий "вариант завершён после дедлайна" без авто-expire логики:
        # завершаем вариант напрямую и создаём сабмиты с полным баллом.
        a.is_completed = True
        a.save(update_fields=["is_completed"])
        for t in self.tasks:
            Submission.objects.create(
                student=self.student,
                task=t,
                assignment=a,
                score=2,
                primary_score=2,
                is_correct=True,
            )

        from core.analytics import calibrate_learning_velocity_for_assignment

        self.assertTrue(calibrate_learning_velocity_for_assignment(a))

        self.profile.refresh_from_db()
        # 0.018 * deadline_weight(0.2) => 0.0036
        self.assertAlmostEqual(float(self.profile.learning_velocity), 1.0036, places=4)
