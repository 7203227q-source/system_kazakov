from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Assignment, ExamFormat, SpacedRepetition, Subject, Task, TaskType, TaskVariant, Topic, User


class StudentTaskErrorButtonsTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.tutor.students.add(self.student)
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(
            topic=topic,
            task_type=task_type,
            correct_answer="1",
            difficulty=10,
            exam_points=1,
        )
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        self.assignment = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="A",
            is_draft=False,
            exam_format=exam,
        )
        self.assignment.tasks.add(self.task)
        SpacedRepetition.objects.create(student=self.student, task=self.task, next_review_date=timezone.localdate())

    def test_practice_page_contains_error_button(self):
        self.client.force_login(self.student)
        res = self.client.get(reverse("student_practice"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Ошибка")
        self.assertContains(res, 'data-error-source="practice"')

    def test_srs_page_contains_error_button(self):
        self.client.force_login(self.student)
        res = self.client.get(reverse("student_practice") + "?mode=srs")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'data-error-source="srs"')

    def test_assignment_page_contains_per_task_error_button(self):
        self.client.force_login(self.student)
        res = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'data-error-source="variant"')
        self.assertContains(res, f'data-task-id="{self.task.id}"')
