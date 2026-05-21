from django.test import TestCase
from django.urls import reverse

from core.models import (
    Assignment,
    DailySnapshot,
    ExamFormat,
    SpacedRepetition,
    StudentSubjectProfile,
    Subject,
    Submission,
    Task,
    TaskLog,
    TaskType,
    Topic,
    User,
)


class TutorResetStudentSubjectStatsTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor.students.add(self.student)

        self.subj_x = Subject.objects.create(name="Математика")
        self.ef_x = ExamFormat.objects.create(subject=self.subj_x, name="ЕГЭ", year=2026, is_active=True)
        self.topic_x = Topic.objects.create(subject=self.subj_x, name="T")
        self.tt_x = TaskType.objects.create(exam_format=self.ef_x, number=1, name="1", max_points=1)
        self.task_x1 = Task.objects.create(
            topic=self.topic_x, task_type=self.tt_x, correct_answer="1", difficulty=10, exam_points=1
        )
        self.task_x2 = Task.objects.create(
            topic=self.topic_x, task_type=self.tt_x, correct_answer="1", difficulty=10, exam_points=1
        )

        self.subj_y = Subject.objects.create(name="Физика")
        self.ef_y = ExamFormat.objects.create(subject=self.subj_y, name="ЕГЭ физика", year=2026, is_active=True)
        self.topic_y = Topic.objects.create(subject=self.subj_y, name="TY")
        self.tt_y = TaskType.objects.create(exam_format=self.ef_y, number=1, name="1", max_points=1)
        self.task_y = Task.objects.create(
            topic=self.topic_y, task_type=self.tt_y, correct_answer="1", difficulty=10, exam_points=1
        )

    def test_reset_maximum(self):
        p = StudentSubjectProfile.objects.create(
            student=self.student,
            subject=self.subj_x,
            exam_format=self.ef_x,
            target_score=80,
            xp=250,
            level=3,
            current_streak=7,
            avg_model_error=1.5,
            trust_factor=0.2,
            learning_velocity=0.3,
        )
        DailySnapshot.objects.create(
            student=self.student, subject=self.subj_x, current_mastery=55.0, predicted_exam_score=60.0
        )
        TaskLog.objects.create(student=self.student, task=self.task_x1, score=1)
        TaskLog.objects.create(student=self.student, task=self.task_y, score=1)
        SpacedRepetition.objects.create(student=self.student, task=self.task_x1)
        SpacedRepetition.objects.create(student=self.student, task=self.task_y)
        Submission.objects.create(student=self.student, task=self.task_x1, user_answer="1", is_correct=True, score=1)
        Submission.objects.create(student=self.student, task=self.task_y, user_answer="1", is_correct=True, score=1)

        a_only_x = Assignment.objects.create(
            tutor=self.tutor, student=self.student, title="AX", is_draft=False, is_completed=False, exam_format=self.ef_x
        )
        a_only_x.tasks.add(self.task_x1, self.task_x2)
        a_mixed = Assignment.objects.create(
            tutor=self.tutor, student=self.student, title="AM", is_draft=False, is_completed=False, exam_format=self.ef_x
        )
        a_mixed.tasks.add(self.task_x1, self.task_y)

        self.client.login(username="t", password="pass")
        url = reverse("tutor_reset_student_subject_stats", args=[self.student.id, self.subj_x.id])
        res = self.client.post(url, data={"confirm": "1"})
        self.assertEqual(res.status_code, 302)

        p.refresh_from_db()
        self.assertEqual(p.xp, 0)
        self.assertEqual(p.level, 1)
        self.assertEqual(p.current_streak, 0)
        self.assertEqual(p.trust_factor, 0.6)
        self.assertEqual(p.learning_velocity, 1.0)
        self.assertEqual(p.avg_model_error, 0.0)
        self.assertIsNone(p.last_verified_date)
        self.assertIsNone(p.last_streak_date)
        self.assertEqual(p.target_score, 80)
        self.assertEqual(p.exam_format_id, self.ef_x.id)

        self.assertEqual(DailySnapshot.objects.filter(student=self.student, subject=self.subj_x).count(), 0)
        self.assertEqual(TaskLog.objects.filter(student=self.student, task__topic__subject=self.subj_x).count(), 0)
        self.assertEqual(SpacedRepetition.objects.filter(student=self.student, task__topic__subject=self.subj_x).count(), 0)
        self.assertEqual(Submission.objects.filter(student=self.student, task__topic__subject=self.subj_x).count(), 0)

        a_only_x.refresh_from_db()
        self.assertTrue(a_only_x.is_deleted)
        self.assertEqual(a_only_x.deleted_by_id, self.tutor.id)
        self.assertIsNotNone(a_only_x.deleted_at)

        a_mixed.refresh_from_db()
        self.assertFalse(a_mixed.is_deleted)

    def test_requires_confirm_param(self):
        self.client.login(username="t", password="pass")
        url = reverse("tutor_reset_student_subject_stats", args=[self.student.id, self.subj_x.id])
        res = self.client.post(url, data={})
        self.assertEqual(res.status_code, 400)

    def test_forbidden_for_non_tutor(self):
        other = User.objects.create_user(username="p", password="pass", role="parent")
        self.client.force_login(other)
        url = reverse("tutor_reset_student_subject_stats", args=[self.student.id, self.subj_x.id])
        res = self.client.post(url, data={"confirm": "1"})
        self.assertEqual(res.status_code, 403)

    def test_forbidden_for_other_tutor(self):
        other_tutor = User.objects.create_user(username="t2", password="pass", role="tutor")
        self.client.force_login(other_tutor)
        url = reverse("tutor_reset_student_subject_stats", args=[self.student.id, self.subj_x.id])
        res = self.client.post(url, data={"confirm": "1"})
        self.assertEqual(res.status_code, 403)

