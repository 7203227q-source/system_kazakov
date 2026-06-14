from django.db import IntegrityError
from django.test import TestCase

from core.models import (
    CurriculumTopic,
    CurriculumUnit,
    LearningTaskType,
    LearningTrack,
    SchoolTaskMeta,
    Subject,
    Task,
    Topic,
)


class SchoolTrackModelTests(TestCase):
    def test_seeded_math_grade7_track_exists(self):
        learning_track = LearningTrack.objects.get(
            mode="school",
            grade=7,
            title="Математика, 7 класс",
        )

        self.assertEqual(learning_track.subject.name, "Математика")
        self.assertTrue(learning_track.is_active)

    def test_curriculum_topic_order_is_scoped_to_unit(self):
        subject = Subject.objects.create(name="Алгебра")
        learning_track = LearningTrack.objects.create(
            subject=subject,
            mode="school",
            grade=7,
            title="Алгебра, 7 класс",
        )
        unit = CurriculumUnit.objects.create(
            learning_track=learning_track,
            title="Рациональные числа",
            position=1,
        )
        CurriculumTopic.objects.create(
            unit=unit,
            title="Обыкновенные дроби",
            position=1,
            is_required=True,
        )

        with self.assertRaises(IntegrityError):
            CurriculumTopic.objects.create(
                unit=unit,
                title="Десятичные дроби",
                position=1,
                is_required=True,
            )

    def test_school_task_meta_allows_task_without_exam_format(self):
        subject = Subject.objects.create(name="Математика")
        learning_track = LearningTrack.objects.create(
            subject=subject,
            mode="school",
            grade=7,
            title="Математика, 7 класс",
        )
        unit = CurriculumUnit.objects.create(
            learning_track=learning_track,
            title="Уравнения",
            position=1,
        )
        curriculum_topic = CurriculumTopic.objects.create(
            unit=unit,
            title="Линейные уравнения",
            position=1,
            is_required=True,
        )
        learning_task_type = LearningTaskType.objects.create(
            learning_track=learning_track,
            code="linear-basic",
            name="Уравнение в одно действие",
            default_max_points=1,
            is_extended_answer=False,
        )
        legacy_topic = Topic.objects.create(subject=subject, name="Линейные уравнения")
        task = Task.objects.create(
            topic=legacy_topic,
            correct_answer="5",
            difficulty=20,
            exam_points=1,
        )

        school_task_meta = SchoolTaskMeta.objects.create(
            task=task,
            learning_track=learning_track,
            curriculum_topic=curriculum_topic,
            learning_task_type=learning_task_type,
            difficulty_level=2,
            status="published",
        )

        self.assertEqual(school_task_meta.learning_track.title, "Математика, 7 класс")
        self.assertIsNone(task.task_type)
