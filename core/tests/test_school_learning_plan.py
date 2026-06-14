from django.test import TestCase
from django.urls import reverse

from core.models import CurriculumTopic, CurriculumUnit, LearningTrack, StudentLearningPlan, Subject, User
from core.services_school_plan import (
    collect_diagnostic_scores_for_track,
    create_initial_learning_plan,
    update_learning_plan_after_result,
)


class SchoolLearningPlanTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="student", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        self.track = LearningTrack.objects.create(subject=subject, mode="school", grade=7, title="Математика, 7 класс")
        unit = CurriculumUnit.objects.create(learning_track=self.track, title="Уравнения", position=1)
        self.topic1 = CurriculumTopic.objects.create(unit=unit, title="Уравнение в одно действие", position=1, is_required=True)
        self.topic2 = CurriculumTopic.objects.create(unit=unit, title="Уравнение в два действия", position=2, is_required=True)

    def test_create_initial_learning_plan_orders_topics_by_diagnostic_score(self):
        plan = create_initial_learning_plan(
            student=self.student,
            track=self.track,
            diagnostic_scores={
                self.topic1.id: 0.2,
                self.topic2.id: 0.8,
            },
            goal_type="подтянуть базу",
        )

        self.assertIsInstance(plan, StudentLearningPlan)
        items = list(plan.items.order_by("-priority", "id"))
        self.assertEqual(items[0].curriculum_topic_id, self.topic1.id)
        self.assertEqual(items[0].status, "assigned")

    def test_update_learning_plan_after_result_schedules_repeat_for_low_accuracy(self):
        plan = create_initial_learning_plan(
            student=self.student,
            track=self.track,
            diagnostic_scores={self.topic1.id: 0.4, self.topic2.id: 0.6},
            goal_type="идти по школьной программе",
        )
        item = plan.items.get(curriculum_topic=self.topic1)

        update_learning_plan_after_result(item=item, accuracy=0.3)
        item.refresh_from_db()

        self.assertEqual(item.status, "repeat")
        self.assertIsNotNone(item.next_review_at)

    def test_collect_diagnostic_scores_for_track_ignores_blank_values(self):
        scores = collect_diagnostic_scores_for_track(
            track=self.track,
            data={
                f"topic_{self.topic1.id}": "0.45",
                f"topic_{self.topic2.id}": "",
            },
        )

        self.assertEqual(scores, {self.topic1.id: 0.45})


class SchoolDiagnosticStartTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="tutor", password="pass", role="tutor")
        self.student = User.objects.create_user(username="student-plan", password="pass", role="student")
        self.tutor.students.add(self.student)
        subject = Subject.objects.create(name="Алгебра")
        self.track = LearningTrack.objects.create(subject=subject, mode="school", grade=7, title="Алгебра, 7 класс")
        unit = CurriculumUnit.objects.create(learning_track=self.track, title="Уравнения", position=1)
        self.topic = CurriculumTopic.objects.create(unit=unit, title="Линейные уравнения", position=1, is_required=True)
        self.topic2 = CurriculumTopic.objects.create(unit=unit, title="Задачи на уравнения", position=2, is_required=True)

    def test_tutor_can_start_plan_from_diagnostic_scores(self):
        self.client.login(username="tutor", password="pass")

        response = self.client.post(
            reverse("tutor_start_school_plan", args=[self.student.id]),
            {
                "learning_track": self.track.id,
                f"topic_{self.topic.id}": "0.25",
                f"topic_{self.topic2.id}": "0.9",
                "goal_type": "подтянуть базу",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("tutor_student_history", args=[self.student.id]))

        plan = StudentLearningPlan.objects.get(student=self.student, learning_track=self.track)
        self.assertEqual(plan.goal_type, "подтянуть базу")
        self.assertEqual(plan.created_by, self.tutor)
        self.assertIsNotNone(plan.diagnostic_completed_at)
        self.assertEqual(
            list(plan.items.order_by("-priority").values_list("curriculum_topic_id", flat=True)),
            [self.topic.id, self.topic2.id],
        )

    def test_unlinked_tutor_cannot_start_plan(self):
        other_tutor = User.objects.create_user(username="other-tutor", password="pass", role="tutor")
        self.client.login(username="other-tutor", password="pass")

        response = self.client.post(
            reverse("tutor_start_school_plan", args=[self.student.id]),
            {
                "learning_track": self.track.id,
                f"topic_{self.topic.id}": "0.25",
                "goal_type": "подтянуть базу",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(StudentLearningPlan.objects.filter(student=self.student, created_by=other_tutor).exists())
