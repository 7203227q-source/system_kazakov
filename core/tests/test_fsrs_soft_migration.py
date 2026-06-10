from django.test import TestCase
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, Subject, Task, TaskType, Topic, User
from core.services import process_task_submission


class FSRSSoftMigrationTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="fsrs_s", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тест", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(
            topic=topic,
            task_type=task_type,
            correct_answer="42",
            difficulty=40,
            exam_points=1,
        )

    def test_new_record_is_created_as_fsrs(self):
        rec = process_task_submission(
            self.student,
            self.task,
            grade=5,
            active_time_seconds=35,
            attempt_count=1,
        )
        self.assertEqual(rec.srs_algorithm, "fsrs")
        self.assertIsInstance(rec.fsrs_state, dict)
        self.assertTrue(rec.fsrs_state)
        self.assertGreaterEqual(rec.next_review_date, timezone.localdate())

    def test_legacy_sm2_record_is_soft_migrated_on_next_review(self):
        legacy = SpacedRepetition.objects.create(
            student=self.student,
            task=self.task,
            easiness_factor=2.5,
            interval=6,
            repetitions=2,
            next_review_date=timezone.localdate(),
        )
        self.assertFalse(bool(getattr(legacy, "fsrs_state", None)))
        self.assertEqual(getattr(legacy, "srs_algorithm", "sm2"), "sm2")

        rec = process_task_submission(
            self.student,
            self.task,
            grade=1,
            active_time_seconds=75,
            attempt_count=2,
        )
        self.assertEqual(rec.id, legacy.id)
        self.assertEqual(rec.srs_algorithm, "fsrs")
        self.assertIsInstance(rec.fsrs_state, dict)
        self.assertTrue(rec.fsrs_state)
