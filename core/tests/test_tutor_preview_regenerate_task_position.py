from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User


class TutorPreviewRegenerateTaskPositionTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor.students.add(self.student)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subj, name="T")
        self.tt = TaskType.objects.create(exam_format=ef, number=1, name="Тригонометрия", max_points=1, is_extended_answer=False)

        self.t1 = Task.objects.create(topic=topic, task_type=self.tt, correct_answer="1", difficulty=10, exam_points=1)
        self.t2 = Task.objects.create(topic=topic, task_type=self.tt, correct_answer="2", difficulty=10, exam_points=1)
        self.t3 = Task.objects.create(topic=topic, task_type=self.tt, correct_answer="3", difficulty=10, exam_points=1)
        self.t4 = Task.objects.create(topic=topic, task_type=self.tt, correct_answer="4", difficulty=10, exam_points=1)

        for t in [self.t1, self.t2, self.t3, self.t4]:
            TaskVariant.objects.create(task=t, theme="classic", content=f"<p>Task {t.correct_answer}</p>", solution="")

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="Вариант 1", is_draft=True, exam_format=ef)
        self.assignment.tasks.add(self.t1, self.t2, self.t3)

    def test_preview_shows_task_type_number_and_name(self):
        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_preview_assignment", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "№1.")
        self.assertContains(res, "Тригонометрия")

    def test_regenerate_keeps_task_position(self):
        self.client.login(username="t", password="pass")
        regen = self.client.post(reverse("tutor_regenerate_task", args=[self.assignment.id, self.t2.id]))
        self.assertEqual(regen.status_code, 302)
        self.assignment.refresh_from_db()

        self.assertFalse(self.assignment.tasks.filter(id=self.t2.id).exists())
        self.assertTrue(self.assignment.tasks.filter(id=self.t4.id).exists())

        page = self.client.get(reverse("tutor_preview_assignment", args=[self.assignment.id]))
        html = page.content.decode("utf-8")
        p1 = html.find(f'id="task-{self.t1.id}"')
        p2 = html.find(f'id="task-{self.t4.id}"')
        p3 = html.find(f'id="task-{self.t3.id}"')
        self.assertTrue(p1 != -1 and p2 != -1 and p3 != -1)
        self.assertLess(p1, p2)
        self.assertLess(p2, p3)

