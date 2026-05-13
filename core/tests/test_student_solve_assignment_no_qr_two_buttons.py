from django.test import TestCase
from django.urls import reverse

from bs4 import BeautifulSoup

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User


class StudentSolveAssignmentNoQRTwoButtonsTests(TestCase):
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

    def test_part2_has_two_upload_buttons_and_no_qr(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.content, "html.parser")

        self.assertIsNone(soup.select_one(f"#qr_block_{self.task.id}"))
        self.assertIsNotNone(soup.select_one(f"#camera_file_{self.task.id}"))
        self.assertIsNotNone(soup.select_one(f"#gallery_file_{self.task.id}"))

