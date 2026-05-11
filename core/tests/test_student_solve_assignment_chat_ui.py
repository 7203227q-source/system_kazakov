from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, Topic, User


class StudentSolveAssignmentChatUiTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor.students.add(self.student)

        self.subject = Subject.objects.create(name="Математика")
        self.fmt = ExamFormat.objects.create(subject=self.subject, name="ОГЭ математика", year=2026, is_active=True)
        self.tt = TaskType.objects.create(exam_format=self.fmt, number=1, name="Тип 1", max_points=1)
        self.topic = Topic.objects.create(subject=self.subject, name="Т")
        self.task = Task.objects.create(topic=self.topic, task_type=self.tt, subtype_tag="x", correct_answer="1", difficulty=10, exam_points=1)

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="Вариант 1", is_draft=False)
        self.assignment.tasks.add(self.task)

    def test_chat_hidden_until_task_checked(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, f'id="chat_block_{self.task.id}"')
        self.assertContains(res, f'id="chat_block_{self.task.id}" class="hidden')

    def test_chat_visible_after_task_checked(self):
        Submission.objects.create(student=self.student, task=self.task, assignment=self.assignment, user_answer="1", is_correct=True, score=1)
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, f'id="comment_text_{self.task.id}"')
        self.assertNotContains(res, f'id="chat_block_{self.task.id}" class="hidden')
