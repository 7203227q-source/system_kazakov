from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, StudentSubjectProfile, Subject, Task, TaskType, Topic, User


class AssignmentTitleAutogenTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        self.ef = ExamFormat.objects.create(subject=subj, name="ОГЭ математика", year=2026, is_active=True)
        StudentSubjectProfile.objects.create(student=self.student, subject=subj, exam_format=self.ef)

        tt = TaskType.objects.create(exam_format=self.ef, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subj, name="T")
        self.task = Task.objects.create(
            topic=topic,
            task_type=tt,
            subtype_tag="Без темы",
            correct_answer="1",
            difficulty=10,
            exam_points=1,
        )

    def _post(self):
        return self.client.post(
            reverse("tutor_create_assignment"),
            {
                "student_id": str(self.student.id),
                "exam_format": str(self.ef.id),
                "kind": "homework",
                "title": "",
                f"type_count_{self.task.task_type_id}": "1",
                "subtype_checked_1": "on",
                "subtype_name_1": self.task.subtype_tag or "",
                "subtype_type_1": str(self.task.task_type_id),
            },
        )

    def test_autogen_title_prefix_and_seq(self):
        self.client.login(username="t", password="pass")
        res = self._post()
        self.assertEqual(res.status_code, 302)

        a = Assignment.objects.latest("id")
        self.assertEqual(a.student_id, self.student.id)
        self.assertEqual(a.exam_format_id, self.ef.id)
        self.assertEqual(a.kind, "homework")
        self.assertEqual(a.student_seq, 1)
        self.assertTrue(a.title.startswith("ОГЭ математика 2026 — "))
        self.assertIn(" — Домашняя работа №1", a.title)

    def test_seq_increments_per_student(self):
        self.client.login(username="t", password="pass")
        self._post()
        self._post()
        a = Assignment.objects.latest("id")
        self.assertEqual(a.student_seq, 2)
        self.assertIn("№2", a.title)

