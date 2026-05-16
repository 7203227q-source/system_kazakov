from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User


class StudentSolveAssignmentForceFinishPart2Tests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subj, name="T")

        tt_part2 = TaskType.objects.create(
            exam_format=ef,
            number=20,
            name="2 часть",
            max_points=2,
            is_extended_answer=True,
        )
        self.part2_task = Task.objects.create(
            topic=topic,
            task_type=tt_part2,
            correct_answer="x",
            difficulty=10,
            exam_points=2,
        )

        self.assignment = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="A",
            is_draft=False,
            is_deleted=False,
            due_date=timezone.now().date(),
            exam_format=ef,
        )
        self.assignment.tasks.add(self.part2_task)

    def test_finish_requires_confirmation_when_part2_missing_photo(self):
        self.client.login(username="s", password="pass")
        res = self.client.post(
            reverse("student_solve_assignment", args=[self.assignment.id]),
            data={"action": "finish"},
        )
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")
        self.assertIn("Завершить всё равно", html)

        self.assignment.refresh_from_db()
        self.assertFalse(self.assignment.is_completed)

    def test_force_finish_completes_assignment(self):
        self.client.login(username="s", password="pass")
        res = self.client.post(
            reverse("student_solve_assignment", args=[self.assignment.id]),
            data={"action": "finish", "force_finish": "1"},
            follow=False,
        )
        self.assertIn(res.status_code, (302, 303))

        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_completed)

