from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User


class OGEMathFormatNameWithoutMathTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subj, name="T")

        # Номер 20 — это развёрнутая часть ОГЭ, даже если max_points=2
        tt20 = TaskType.objects.create(exam_format=ef, number=20, name="№20", max_points=2, is_extended_answer=False)
        task20 = Task.objects.create(topic=topic, task_type=tt20, correct_answer="1", difficulty=10, exam_points=2)

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=ef)
        self.assignment.tasks.add(task20)

    def test_task20_requires_photo_block(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        # Для развёрнутой части должен быть блок загрузки фото, а не поле ответа
        self.assertContains(res, "Загрузите решение")

