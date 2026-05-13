import uuid

from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, Submission, User


class StudentSolveAssignmentDesktopUploadTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ математика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=20, name="Развернутый ответ", max_points=2)
        topic = Topic.objects.create(subject=subj, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=ef)
        self.assignment.tasks.add(self.task)

        self.token = uuid.UUID("11111111-1111-1111-1111-111111111111")
        Submission.objects.create(student=self.student, assignment=self.assignment, task=self.task, upload_token=self.token)

    def test_page_contains_desktop_upload_handler(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, f"desktop_file_{self.task.id}")
        self.assertContains(res, "capture=\"environment\"")
        self.assertContains(res, str(self.token))
        self.assertContains(res, "/upload/")
        self.assertContains(res, "addEventListener('change'")
