from django.test import TestCase
from django.urls import reverse

from bs4 import BeautifulSoup

from core.models import (
    Assignment,
    ExamFormat,
    ExamScoreScale,
    StudentSubjectProfile,
    Subject,
    Submission,
    Task,
    TaskType,
    Topic,
    User,
)


class AssignmentSummaryExamFormatScoringTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        self.subject = Subject.objects.create(name="Математика")
        self.ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ математика", year=2026, is_active=True)
        ExamScoreScale.objects.create(
            exam_format=self.ef,
            max_primary_score=31,
            grade_rules=[
                {"grade": 2, "min_total": 0, "max_total": 7, "min_geometry": None},
                {"grade": 3, "min_total": 8, "max_total": 14, "min_geometry": 2},
                {"grade": 4, "min_total": 15, "max_total": 21, "min_geometry": 2},
                {"grade": 5, "min_total": 22, "max_total": 31, "min_geometry": 2},
            ],
        )

        StudentSubjectProfile.objects.create(student=self.student, subject=self.subject, exam_format=self.ef)

        tt1 = TaskType.objects.create(exam_format=self.ef, number=1, name="Тип 1", max_points=1, is_geometry=False)
        tt15 = TaskType.objects.create(exam_format=self.ef, number=15, name="Тип 15", max_points=1, is_geometry=True)
        TaskType.objects.create(exam_format=self.ef, number=16, name="Тип 16", max_points=1, is_geometry=True)
        TaskType.objects.create(exam_format=self.ef, number=17, name="Тип 17", max_points=1, is_geometry=True)
        TaskType.objects.create(exam_format=self.ef, number=18, name="Тип 18", max_points=1, is_geometry=True)
        TaskType.objects.create(exam_format=self.ef, number=19, name="Тип 19", max_points=1, is_geometry=True)

        topic = Topic.objects.create(subject=self.subject, name="T")
        self.task1 = Task.objects.create(topic=topic, task_type=tt1, correct_answer="1", difficulty=10, exam_points=1)
        self.task2 = Task.objects.create(topic=topic, task_type=tt15, correct_answer="1", difficulty=10, exam_points=1)

        self.assignment = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="Вариант",
            is_completed=True,
            is_draft=False,
            exam_format=None,
        )
        self.assignment.tasks.add(self.task1, self.task2)

        Submission.objects.create(student=self.student, task=self.task1, assignment=self.assignment, is_correct=True, user_answer="1")
        Submission.objects.create(student=self.student, task=self.task2, assignment=self.assignment, is_correct=True, user_answer="1")

    def test_student_summary_uses_student_exam_format_scale_and_grade(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_assignment_summary", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.content, "html.parser")
        txt = " ".join(soup.get_text(" ").split())
        self.assertIn("31/31", txt.replace(" ", ""))
        self.assertIn("оценка 5", txt)

    def test_tutor_summary_uses_student_exam_format_scale_and_grade(self):
        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_assignment_summary", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.content, "html.parser")
        txt = " ".join(soup.get_text(" ").split())
        self.assertIn("31/31", txt.replace(" ", ""))
        self.assertIn("оценка 5", txt)
