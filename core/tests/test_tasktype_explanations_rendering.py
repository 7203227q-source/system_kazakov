from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User


class TaskTypeExplanationRenderingTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create(username="t", role="tutor")
        self.student = User.objects.create(username="s", role="student")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1, explanation="Пояснение")
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="0")
        TaskVariant.objects.create(task=task, theme="classic", content="<p>x</p>", solution="<p>y</p>")
        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="Вариант", exam_format=exam)
        self.assignment.tasks.add(task)

    def test_student_variant_shows_explanation(self):
        self.client.force_login(self.student)
        res = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        self.assertIn("Пояснение", res.content.decode("utf-8"))

