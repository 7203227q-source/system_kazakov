from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, Submission, User


class EGEPhysicsStructureTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        self.physics = Subject.objects.create(name="Физика")
        self.ef = ExamFormat.objects.create(subject=self.physics, name="ЕГЭ физика", year=2026, is_active=True)
        topic = Topic.objects.create(subject=self.physics, name="T")

        # Тестовая задача на 2 балла (часть 1)
        self.tt_test2 = TaskType.objects.create(
            exam_format=self.ef, number=6, name="Тест (2 балла)", max_points=2, is_extended_answer=False
        )
        self.task_test2 = Task.objects.create(topic=topic, task_type=self.tt_test2, correct_answer="1", difficulty=10, exam_points=2)

        # Развёрнутая задача (часть 2)
        self.tt_ext = TaskType.objects.create(
            exam_format=self.ef, number=21, name="Развёрнутая", max_points=3, is_extended_answer=True
        )
        self.task_ext = Task.objects.create(topic=topic, task_type=self.tt_ext, correct_answer="1", difficulty=10, exam_points=3)

        self.assignment = Assignment.objects.create(
            tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=self.ef
        )
        self.assignment.tasks.add(self.task_test2, self.task_ext)

    def test_part1_2points_does_not_require_photo(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, f'name="answer_{self.task_test2.id}"')

    def test_finish_requires_photo_only_for_extended(self):
        self.client.login(username="s", password="pass")
        Submission.objects.create(student=self.student, assignment=self.assignment, task=self.task_ext)
        res = self.client.post(
            reverse("student_solve_assignment", args=[self.assignment.id]),
            data={"action": "finish", f"answer_{self.task_test2.id}": "1"},
            follow=False,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("Завершить всё равно", res.content.decode("utf-8"))
