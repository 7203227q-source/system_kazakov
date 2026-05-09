from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User, TaskVariant, WhiteboardSession


class WhiteboardAccessTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username='tutor1', password='x', role='tutor')
        self.student = User.objects.create_user(username='student1', password='x', role='student')
        self.other_student = User.objects.create_user(username='student2', password='x', role='student')
        self.other_tutor = User.objects.create_user(username='tutor2', password='x', role='tutor')

        subject = Subject.objects.create(name='Математика')
        exam_format = ExamFormat.objects.create(subject=subject, name='ЕГЭ', year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name='Тест', max_points=1)
        topic = Topic.objects.create(subject=subject, name='Тема')
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer='42', difficulty=50, exam_points=1)
        TaskVariant.objects.create(task=self.task, theme='classic', content='<p>Условие</p>', solution='<p>Решение</p>')

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title='Вариант 1', is_draft=False)
        self.assignment.tasks.add(self.task)

        self.session = WhiteboardSession.objects.create(student=self.student, tutor=self.tutor, assignment=self.assignment, task=self.task)

    def test_student_can_open_own_board_page(self):
        self.client.force_login(self.student)
        r = self.client.get(reverse('whiteboard_page', args=[self.session.id]))
        self.assertEqual(r.status_code, 200)

    def test_other_student_cannot_open_board_page(self):
        self.client.force_login(self.other_student)
        r = self.client.get(reverse('whiteboard_page', args=[self.session.id]))
        self.assertIn(r.status_code, (302, 403))

    def test_tutor_can_open_own_student_board_page(self):
        self.client.force_login(self.tutor)
        r = self.client.get(reverse('whiteboard_page', args=[self.session.id]))
        self.assertEqual(r.status_code, 200)

    def test_other_tutor_cannot_pull_events(self):
        self.client.force_login(self.other_tutor)
        r = self.client.get(reverse('whiteboard_events_pull', args=[self.session.id]), {'after': 0})
        self.assertEqual(r.status_code, 403)

    def test_list_requires_correct_student(self):
        self.client.force_login(self.student)
        r = self.client.get(reverse('whiteboard_list'), {'student_id': self.other_student.id, 'assignment_id': self.assignment.id, 'task_id': self.task.id})
        self.assertEqual(r.status_code, 403)

