from django.test import TestCase
from django.urls import reverse

from core.models import (
    Assignment,
    ExamFormat,
    SpacedRepetition,
    Subject,
    Task,
    TaskType,
    TaskVariant,
    Topic,
    User,
)


class SrsFromAssignmentsTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='srs_student', password='x', role='student')
        self.tutor = User.objects.create_user(username='srs_tutor', password='x', role='tutor')
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name='Математика')
        ef = ExamFormat.objects.create(subject=subj, name='ЕГЭ', year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name='Тест', max_points=1)
        topic = Topic.objects.create(subject=subj, name='T')
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer='42', difficulty=50, exam_points=1)
        TaskVariant.objects.create(task=self.task, theme='classic', content='<p>U</p>', solution='<p>S</p>')

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title='A', is_draft=False)
        self.assignment.tasks.add(self.task)

    def test_wrong_answer_in_assignment_creates_srs_record(self):
        self.client.force_login(self.student)
        url = reverse('student_check_assignment_task', args=[self.assignment.id, self.task.id])
        self.client.post(url, {'answer': '0'})
        self.assertTrue(SpacedRepetition.objects.filter(student=self.student, task=self.task).exists())

    def test_manual_add_to_srs_endpoint(self):
        self.client.force_login(self.student)
        url = reverse('student_srs_add', args=[self.task.id])
        self.client.post(url)
        self.assertTrue(SpacedRepetition.objects.filter(student=self.student, task=self.task).exists())

