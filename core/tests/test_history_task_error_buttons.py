from django.test import TestCase
from django.urls import reverse

from core.models import (
    Assignment,
    ExamFormat,
    Subject,
    Submission,
    Task,
    TaskErrorReport,
    TaskType,
    TaskVariant,
    Topic,
    User,
)


class HistoryTaskErrorButtonsTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.tutor.students.add(self.student)
        subject = Subject.objects.create(name="Физика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="1", exam_points=1)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        self.assignment = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="Вариант",
            is_draft=False,
            exam_format=exam,
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

    def test_student_history_contains_error_button_and_post_script(self):
        self.client.force_login(self.student)
        res = self.client.get(reverse("student_history"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'data-error-source="student_history"')
        self.assertContains(res, f'data-submission-id="{self.submission.id}"')
        self.assertContains(res, 'data-assignment-id="%s"' % self.assignment.id)
        self.assertContains(res, "report-error/")
        self.assertContains(res, "method: 'POST'")

    def test_student_history_uses_server_state_for_existing_report(self):
        TaskErrorReport.objects.create(
            task=self.task,
            reported_by=self.student,
            reporter_role="student",
            source="student_history",
            submission=self.submission,
            assignment=self.assignment,
        )
        self.client.force_login(self.student)
        res = self.client.get(reverse("student_history"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'data-error-reported="1"')
        self.assertContains(res, "Ошибка отмечена")

    def test_tutor_history_contains_error_button_and_post_script(self):
        self.client.force_login(self.tutor)
        res = self.client.get(reverse("tutor_student_history", args=[self.student.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'data-error-source="tutor_history"')
        self.assertContains(res, f'data-submission-id="{self.submission.id}"')
        self.assertContains(res, 'data-assignment-id="%s"' % self.assignment.id)
        self.assertContains(res, "report-error/")
        self.assertContains(res, "method: 'POST'")

    def test_tutor_history_uses_server_state_for_existing_report(self):
        TaskErrorReport.objects.create(
            task=self.task,
            reported_by=self.tutor,
            reporter_role="tutor",
            source="tutor_history",
            submission=self.submission,
            assignment=self.assignment,
        )
        self.client.force_login(self.tutor)
        res = self.client.get(reverse("tutor_student_history", args=[self.student.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'data-error-reported="1"')
        self.assertContains(res, "Ошибка отмечена")
