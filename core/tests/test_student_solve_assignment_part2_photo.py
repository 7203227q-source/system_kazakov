from django.test import TestCase
from django.urls import reverse

from bs4 import BeautifulSoup

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, Submission, User


class StudentSolveAssignmentPart2PhotoTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ математика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=20, name="Развернутый ответ", max_points=2, is_extended_answer=True)
        topic = Topic.objects.create(subject=subj, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=ef)
        self.assignment.tasks.add(self.task)

    def test_part2_detected_by_tasktype_max_points_and_shows_photo_ui(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Загрузите решение")
        soup = BeautifulSoup(res.content, "html.parser")
        self.assertIsNone(soup.select_one(f"#answer_{self.task.id}"))
        self.assertIsNotNone(soup.select_one(f"#upload_block_{self.task.id}"))
        self.assertTrue(Submission.objects.filter(student=self.student, assignment=self.assignment, task=self.task).exists())
