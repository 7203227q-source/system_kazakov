from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Assignment,
    AssignmentExtensionRequest,
    ExamFormat,
    Subject,
    Task,
    TaskType,
    TaskVariant,
    Topic,
    User,
    Submission,
)


class AssignmentDeadlineTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username='tutor1', password='x', role='tutor')
        self.student = User.objects.create_user(username='student1', password='x', role='student')

        subject = Subject.objects.create(name='Математика')
        exam_format = ExamFormat.objects.create(subject=subject, name='ЕГЭ', year=2026, is_active=True)
        tt1 = TaskType.objects.create(exam_format=exam_format, number=1, name='Тест', max_points=1)
        tt2 = TaskType.objects.create(exam_format=exam_format, number=13, name='Развёрнутая', max_points=4)
        topic = Topic.objects.create(subject=subject, name='Тема')

        self.t1 = Task.objects.create(topic=topic, task_type=tt1, correct_answer='1', difficulty=50, exam_points=1)
        self.t2 = Task.objects.create(topic=topic, task_type=tt2, correct_answer='x', difficulty=50, exam_points=4)
        TaskVariant.objects.create(task=self.t1, theme='classic', content='<p>U1</p>', solution='<p>S1</p>')
        TaskVariant.objects.create(task=self.t2, theme='classic', content='<p>U2</p>', solution='<p>S2</p>')

    def test_overdue_assignment_auto_closes_with_zero_submissions(self):
        a = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title='Вариант 1',
            is_draft=False,
            due_date=timezone.now().date() - timedelta(days=1),
        )
        a.tasks.add(self.t1, self.t2)

        self.client.force_login(self.student)
        self.client.get(reverse('student_dashboard'))

        a.refresh_from_db()
        self.assertTrue(a.is_completed)
        self.assertTrue(a.is_expired)
        self.assertIsNotNone(a.expired_at)

        subs = Submission.objects.filter(assignment=a, student=self.student)
        self.assertEqual(subs.count(), 2)
        for sub in subs:
            self.assertEqual(int(sub.score or 0), 0)

    def test_tutor_approve_extension_reopens_assignment(self):
        a = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title='Вариант 2',
            is_draft=False,
            is_completed=True,
            is_expired=True,
            due_date=timezone.now().date() - timedelta(days=1),
            expired_at=timezone.now(),
        )
        a.tasks.add(self.t1)

        req = AssignmentExtensionRequest.objects.create(
            assignment=a,
            student=self.student,
            tutor=self.tutor,
            requested_days=3,
            comment='Можно продлить?',
            status='pending',
        )

        self.client.force_login(self.tutor)
        self.client.post(reverse('tutor_extension_approve', args=[a.id, req.id]))

        a.refresh_from_db()
        req.refresh_from_db()

        self.assertFalse(a.is_completed)
        self.assertFalse(a.is_expired)
        self.assertIsNone(a.expired_at)
        self.assertEqual(req.status, 'approved')
