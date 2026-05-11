from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User


class StudentSolveAssignmentBackButtonTests(TestCase):
    def test_back_link_does_not_500(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subject = Subject.objects.create(name="Математика")
        fmt = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=fmt, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Т")
        task = Task.objects.create(topic=topic, task_type=tt, subtype_tag="x", correct_answer="1", difficulty=10, exam_points=1)

        a = Assignment.objects.create(tutor=tutor, student=student, title="Вариант 1", is_draft=False)
        a.tasks.add(task)

        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_solve_assignment", args=[a.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, reverse("student_dashboard"))

        res2 = self.client.get(reverse("student_dashboard"))
        self.assertEqual(res2.status_code, 200)

