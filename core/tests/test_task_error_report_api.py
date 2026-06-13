from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class TaskErrorReportApiTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        self.task_type = TaskType.objects.create(exam_format=self.exam, number=1, name="Тест", max_points=1)
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")
        self.task = Task.objects.create(
            topic=self.topic,
            task_type=self.task_type,
            correct_answer="7",
            difficulty=10,
            exam_points=1,
        )
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.admin = User.objects.create_user(username="a", password="pass", role="admin")
        self.tutor.students.add(self.student)
        self.assignment = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="Вариант",
            is_draft=False,
            exam_format=self.exam,
        )
        self.assignment.tasks.add(self.task)
        self.submission = Submission.objects.create(
            student=self.student,
            task=self.task,
            assignment=self.assignment,
            user_answer="0",
            is_correct=False,
            score=0,
        )

    def test_student_can_create_report(self):
        self.client.force_login(self.student)
        res = self.client.post(
            reverse("report_task_error", args=[self.task.id]),
            {"source": "practice"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertJSONEqual(
            res.content,
            {"ok": True, "created": True, "already_reported": False, "report_id": 1},
        )

    def test_second_click_is_idempotent(self):
        self.client.force_login(self.student)
        url = reverse("report_task_error", args=[self.task.id])
        self.client.post(
            url,
            {"source": "variant", "assignment_id": self.assignment.id, "submission_id": self.submission.id},
        )
        res = self.client.post(
            url,
            {"source": "variant", "assignment_id": self.assignment.id, "submission_id": self.submission.id},
        )
        self.assertEqual(res.status_code, 200)
        self.assertJSONEqual(
            res.content,
            {"ok": True, "created": False, "already_reported": True, "report_id": 1},
        )

    def test_tutor_can_create_report_for_student_history_context(self):
        self.client.force_login(self.tutor)
        res = self.client.post(
            reverse("report_task_error", args=[self.task.id]),
            {"source": "tutor_history", "submission_id": self.submission.id, "assignment_id": self.assignment.id},
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '"created": true', status_code=200)

    def test_admin_cannot_create_report(self):
        self.client.force_login(self.admin)
        res = self.client.post(reverse("report_task_error", args=[self.task.id]), {"source": "practice"})
        self.assertEqual(res.status_code, 403)
