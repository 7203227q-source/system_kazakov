from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class AssignmentUnattemptedStatusTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)

        self.task_type_1 = TaskType.objects.create(exam_format=self.exam_format, number=1, name="Тип 1", max_points=1)
        self.task_type_2 = TaskType.objects.create(exam_format=self.exam_format, number=2, name="Тип 2", max_points=2)

        self.topic = Topic.objects.create(subject=self.subject, name="Тема")

        self.task1 = Task.objects.create(
            fipi_id="A1",
            topic=self.topic,
            task_type=self.task_type_1,
            correct_answer="1",
            difficulty=10,
            exam_points=1,
        )
        TaskVariant.objects.create(task=self.task1, theme="classic", content="<p>Q1</p>", solution="<p>S1</p>")

        self.task2 = Task.objects.create(
            fipi_id="A2",
            topic=self.topic,
            task_type=self.task_type_2,
            correct_answer="42",
            difficulty=10,
            exam_points=2,
        )
        TaskVariant.objects.create(task=self.task2, theme="classic", content="<p>Q2</p>", solution="<p>S2</p>")

        self.tutor = User.objects.create_user(username="t1", email="t1@example.com", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s1", email="s1@example.com", password="pass", role="student")
        self.student.draft_check_probability = 0
        self.student.save()

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="Вариант 1")
        self.assignment.tasks.add(self.task1, self.task2)

    def test_finish_does_not_mark_part2_blank_as_incorrect(self):
        Submission.objects.create(student=self.student, task=self.task2, assignment=self.assignment)

        self.client.force_login(self.student)
        res = self.client.post(
            reverse("student_solve_assignment", args=[self.assignment.id]),
            data={
                "action": "finish",
                f"answer_{self.task1.id}": "1",
                f"answer_{self.task2.id}": "",
            },
        )
        self.assertEqual(res.status_code, 302)

        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_completed)

        sub2 = Submission.objects.get(student=self.student, task=self.task2, assignment=self.assignment)
        self.assertIsNone(sub2.is_correct)

        summary = self.client.get(reverse("student_assignment_summary", args=[self.assignment.id]))
        self.assertEqual(summary.status_code, 200)

        html = summary.content.decode("utf-8")
        self.assertIn("Задача №2 (Не решено)", html)
        self.assertNotIn("Задача №2 (Ошибка)", html)

