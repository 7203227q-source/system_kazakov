from django.test import TestCase
from django.urls import reverse

from core.models import (
    Assignment,
    CurriculumTopic,
    CurriculumUnit,
    LearningTaskType,
    LearningTrack,
    SchoolTaskMeta,
    Subject,
    Task,
    Topic,
    User,
)


class SchoolAssignmentFlowTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="tutor", password="pass", role="tutor")
        self.student = User.objects.create_user(username="student", password="pass", role="student")
        self.tutor.students.add(self.student)
        self.subject = Subject.objects.create(name="Математика")
        self.track = LearningTrack.objects.create(
            subject=self.subject,
            mode="school",
            grade=7,
            title="Математика, 7 класс",
        )
        self.unit = CurriculumUnit.objects.create(
            learning_track=self.track,
            title="Уравнения",
            position=1,
        )
        self.curriculum_topic = CurriculumTopic.objects.create(
            unit=self.unit,
            title="Линейные уравнения",
            position=1,
            is_required=True,
        )
        self.learning_type = LearningTaskType.objects.create(
            learning_track=self.track,
            code="linear-basic",
            name="Уравнение в одно действие",
            default_max_points=1,
            is_extended_answer=False,
        )
        legacy_topic = Topic.objects.create(subject=self.subject, name="Линейные уравнения")
        self.task = Task.objects.create(
            topic=legacy_topic,
            correct_answer="7",
            difficulty=20,
            exam_points=1,
        )
        SchoolTaskMeta.objects.create(
            task=self.task,
            learning_track=self.track,
            curriculum_topic=self.curriculum_topic,
            learning_task_type=self.learning_type,
            difficulty_level=2,
            status="published",
        )

    def test_tutor_create_assignment_shows_school_track_filters(self):
        self.client.login(username="tutor", password="pass")

        response = self.client.get(
            reverse("tutor_create_assignment"),
            {"student_id": self.student.id, "mode": "school"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Математика, 7 класс")
        self.assertContains(response, "Линейные уравнения")
        self.assertContains(response, "Уравнение в одно действие")
        self.assertNotContains(response, "Формат экзамена")
        self.assertNotContains(response, "ЕГЭ")

    def test_tutor_can_create_school_assignment_without_exam_format(self):
        self.client.login(username="tutor", password="pass")

        response = self.client.post(
            reverse("tutor_create_assignment"),
            {
                "student_id": self.student.id,
                "mode": "school",
                "learning_track": self.track.id,
                "curriculum_topic": self.curriculum_topic.id,
                "learning_task_type": self.learning_type.id,
                "tasks_per_type": 1,
                "title": "7 класс: линейные уравнения",
            },
        )

        self.assertEqual(response.status_code, 302)
        assignment = Assignment.objects.get(student=self.student)
        self.assertIsNone(assignment.exam_format)
        self.assertEqual(getattr(assignment, "assignment_mode", None), "school")
        self.assertEqual(getattr(assignment, "learning_track_id", None), self.track.id)
        self.assertEqual(getattr(assignment, "curriculum_topic_id", None), self.curriculum_topic.id)
        self.assertEqual(getattr(assignment, "learning_task_type_id", None), self.learning_type.id)
        self.assertEqual(list(assignment.tasks.all()), [self.task])
