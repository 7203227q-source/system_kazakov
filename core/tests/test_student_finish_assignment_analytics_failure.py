from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User


class StudentFinishAssignmentAnalyticsFailureTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ математика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subj, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=ef, is_verified=True)
        self.assignment.tasks.add(self.task)

    def test_finish_does_not_500_if_record_task_log_fails(self):
        from unittest.mock import patch

        self.client.login(username="s", password="pass")
        with patch("core.views.record_task_log", side_effect=Exception("boom")):
            res = self.client.post(
                reverse("student_solve_assignment", args=[self.assignment.id]),
                data={"action": "finish", f"answer_{self.task.id}": "1"},
                follow=False,
            )

        self.assertIn(res.status_code, (302, 303))

