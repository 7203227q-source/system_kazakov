from django.test import TestCase
from django.urls import reverse

from bs4 import BeautifulSoup

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class AssignmentAnswerLockTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=13, name="Тип 13", max_points=1)
        topic = Topic.objects.create(subject=subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="2", difficulty=50, exam_points=1)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>U</p>", solution="<p>S</p>")

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=False)
        self.assignment.tasks.add(self.task)

    def test_second_check_does_not_change_answer_or_result(self):
        self.client.login(username="s", password="pass")
        url = reverse("student_check_assignment_task", args=[self.assignment.id, self.task.id])

        res1 = self.client.post(url, {"answer": "1"})
        self.assertEqual(res1.status_code, 200)
        self.assertFalse(res1.json()["is_correct"])
        self.assertTrue(res1.json().get("locked"))

        sub = Submission.objects.get(student=self.student, assignment=self.assignment, task=self.task)
        self.assertEqual(sub.user_answer, "1")
        self.assertFalse(sub.is_correct)

        res2 = self.client.post(url, {"answer": "2"})
        self.assertEqual(res2.status_code, 200)
        self.assertFalse(res2.json()["is_correct"])
        self.assertTrue(res2.json().get("locked"))

        sub.refresh_from_db()
        self.assertEqual(sub.user_answer, "1")
        self.assertFalse(sub.is_correct)

    def test_input_is_readonly_after_wrong_check(self):
        self.client.login(username="s", password="pass")
        check_url = reverse("student_check_assignment_task", args=[self.assignment.id, self.task.id])
        self.client.post(check_url, {"answer": "1"})

        page = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(page.status_code, 200)
        soup = BeautifulSoup(page.content, "html.parser")
        inp = soup.find("input", {"id": f"answer_{self.task.id}"})
        self.assertIsNotNone(inp)
        self.assertTrue(inp.has_attr("readonly"))

    def test_input_is_readonly_after_correct_check(self):
        self.client.login(username="s", password="pass")
        check_url = reverse("student_check_assignment_task", args=[self.assignment.id, self.task.id])
        self.client.post(check_url, {"answer": "2"})

        page = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(page.status_code, 200)
        soup = BeautifulSoup(page.content, "html.parser")
        inp = soup.find("input", {"id": f"answer_{self.task.id}"})
        self.assertIsNotNone(inp)
        self.assertTrue(inp.has_attr("readonly"))
