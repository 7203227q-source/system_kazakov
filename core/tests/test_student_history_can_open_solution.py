from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User, Submission


class StudentHistoryOpenSolutionTests(TestCase):
    def test_student_history_has_solution_toggle(self):
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")

        task = Task.objects.create(
            fipi_id="X1",
            topic=topic,
            task_type=task_type,
            correct_answer="1",
            difficulty=10,
            exam_points=1,
        )
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>SOLUTION</p>")

        student = User.objects.create_user(username="st1", password="pw", role="student")
        sub = Submission.objects.create(student=student, task=task, user_answer="1", is_correct=True)

        self.client.force_login(student)
        res = self.client.get(reverse("student_history"))

        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Показать решение")
        self.assertContains(res, f'solution_sub_{sub.id}')
        self.assertContains(res, "SOLUTION")

