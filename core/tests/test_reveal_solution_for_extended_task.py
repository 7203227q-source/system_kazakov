from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class RevealSolutionForExtendedTaskTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ математика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=20, name="№20", max_points=2, is_extended_answer=True)
        topic = Topic.objects.create(subject=subj, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>SOLUTION</p>")

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=ef)
        self.assignment.tasks.add(self.task)

        self.sub = Submission.objects.create(student=self.student, assignment=self.assignment, task=self.task)

    def test_reveal_solution_sets_flag_and_returns_solution_html(self):
        self.client.login(username="s", password="pass")
        page = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Не могу решить — показать решение")

        res = self.client.post(reverse("api_submission_reveal_solution", args=[self.sub.id]))
        self.assertEqual(res.status_code, 200)
        self.assertIn("SOLUTION", res.json().get("solution_html", ""))

        self.sub.refresh_from_db()
        self.assertTrue(self.sub.show_solution_allowed)

        page2 = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertContains(page2, "Показать решение (без проверки)")

