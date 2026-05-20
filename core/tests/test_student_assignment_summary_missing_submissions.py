from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, Topic, User


class StudentAssignmentSummaryMissingSubmissionsTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=True)

        tt1 = TaskType.objects.create(exam_format=ef, number=1, name="Тип 1", max_points=1, is_geometry=False)
        tt2 = TaskType.objects.create(exam_format=ef, number=2, name="Тип 2", max_points=2, is_geometry=False)

        topic = Topic.objects.create(subject=subject, name="T")
        self.task1 = Task.objects.create(topic=topic, task_type=tt1, correct_answer="1", difficulty=10, exam_points=1)
        self.task2 = Task.objects.create(topic=topic, task_type=tt2, correct_answer="2", difficulty=10, exam_points=2)

        self.assignment = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="Вариант",
            is_completed=True,
            is_draft=False,
        )
        self.assignment.tasks.add(self.task1, self.task2)

        Submission.objects.create(
            student=self.student,
            task=self.task1,
            assignment=self.assignment,
            is_correct=True,
            user_answer="1",
            score=1,
        )

    def test_summary_does_not_500_when_some_submissions_missing(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_assignment_summary", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)

        self.assertEqual(res.context["max_primary_possible"], 3)
        self.assertEqual(res.context["total_primary_earned"], 1)

        tasks_list = res.context["tasks_list"]
        self.assertEqual(len(tasks_list), 2)
        by_id = {x["task"].id: x for x in tasks_list}
        self.assertIsNotNone(by_id[self.task1.id]["submission"])
        self.assertIsNone(by_id[self.task2.id]["submission"])
        self.assertEqual(by_id[self.task2.id]["points_earned"], 0)

