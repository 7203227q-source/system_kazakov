from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, StudentSubjectProfile, Task, TaskType, Topic, User


class PhysicsKimReferenceWidgetTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")

    def _mk_task(self, *, subject_name: str, exam_format_name: str):
        subj = Subject.objects.create(name=subject_name)
        ef = ExamFormat.objects.create(subject=subj, name=exam_format_name, year=2026, is_active=True)
        topic = Topic.objects.create(subject=subj, name="T")
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1)
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        return subj, ef, task

    def test_assignment_page_shows_widget_for_physics_ege(self):
        subj, ef, task = self._mk_task(subject_name="Физика", exam_format_name="ЕГЭ физика")
        StudentSubjectProfile.objects.create(student=self.student, subject=subj, exam_format=ef)

        a = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="A",
            is_draft=False,
            is_completed=False,
            exam_format=ef,
        )
        a.tasks.add(task)

        self.client.login(username="s", password="pass")
        r = self.client.get(reverse("student_solve_assignment", args=[a.id]))
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="physics-kim-fab"', r.content.decode("utf-8"))

    def test_assignment_page_does_not_show_widget_for_non_physics(self):
        subj, ef, task = self._mk_task(subject_name="Математика", exam_format_name="ЕГЭ математика")
        StudentSubjectProfile.objects.create(student=self.student, subject=subj, exam_format=ef)

        a = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="A",
            is_draft=False,
            is_completed=False,
            exam_format=ef,
        )
        a.tasks.add(task)

        self.client.login(username="s", password="pass")
        r = self.client.get(reverse("student_solve_assignment", args=[a.id]))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('id="physics-kim-fab"', r.content.decode("utf-8"))

    def test_practice_page_shows_widget_for_physics_oge(self):
        subj, ef, task = self._mk_task(subject_name="Физика", exam_format_name="ОГЭ физика")
        StudentSubjectProfile.objects.create(student=self.student, subject=subj, exam_format=ef)

        self.client.login(username="s", password="pass")
        r = self.client.get(reverse("student_practice") + f"?subject_id={subj.id}")
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="physics-kim-fab"', r.content.decode("utf-8"))

