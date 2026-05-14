from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, StudentSubjectProfile, Task, TaskType, Topic, User


class TutorCreateAssignmentSubjectFilterAndPartRangesTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor.students.add(self.student)

        self.subj_phys = Subject.objects.create(name="Физика")
        self.subj_math = Subject.objects.create(name="Математика")

        self.ef_phys = ExamFormat.objects.create(subject=self.subj_phys, name="ЕГЭ", year=2026, is_active=True)
        self.ef_math = ExamFormat.objects.create(subject=self.subj_math, name="ЕГЭ", year=2026, is_active=True)

        StudentSubjectProfile.objects.create(student=self.student, subject=self.subj_phys, exam_format=self.ef_phys)
        StudentSubjectProfile.objects.create(student=self.student, subject=self.subj_math, exam_format=self.ef_math)

        self.topic_phys = Topic.objects.create(subject=self.subj_phys, name="T")
        self.topic_math = Topic.objects.create(subject=self.subj_math, name="T")

        self.tt_phys_1 = TaskType.objects.create(exam_format=self.ef_phys, number=1, name="Физика 1", max_points=1)
        self.tt_phys_26 = TaskType.objects.create(exam_format=self.ef_phys, number=26, name="Физика 26", max_points=4)
        self.tt_math_1 = TaskType.objects.create(exam_format=self.ef_math, number=1, name="Математика 1", max_points=1)
        self.tt_math_19 = TaskType.objects.create(exam_format=self.ef_math, number=19, name="Математика 19", max_points=4)

        Task.objects.create(topic=self.topic_phys, task_type=self.tt_phys_1, correct_answer="1", difficulty=10, exam_points=1, subtype_tag="A")
        Task.objects.create(topic=self.topic_phys, task_type=self.tt_phys_26, correct_answer="1", difficulty=10, exam_points=4, subtype_tag="A")
        Task.objects.create(topic=self.topic_math, task_type=self.tt_math_1, correct_answer="1", difficulty=10, exam_points=1, subtype_tag="A")

    def test_get_filters_task_types_by_selected_exam_format(self):
        self.client.login(username="t", password="pass")
        res = self.client.get(
            reverse("tutor_create_assignment") + f"?student_id={self.student.id}&exam_format={self.ef_phys.id}"
        )
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")
        self.assertIn("Физика 1", html)
        self.assertIn("Физика 26", html)
        self.assertNotIn("Математика 1", html)

    def test_part_ranges_are_derived_from_exam_format(self):
        self.client.login(username="t", password="pass")
        res_phys = self.client.get(
            reverse("tutor_create_assignment") + f"?student_id={self.student.id}&exam_format={self.ef_phys.id}"
        )
        html_phys = res_phys.content.decode("utf-8")
        self.assertIn("Тестовая часть (1-20)", html_phys)
        self.assertIn("Развернутая часть (21-26)", html_phys)

        res_math = self.client.get(
            reverse("tutor_create_assignment") + f"?student_id={self.student.id}&exam_format={self.ef_math.id}"
        )
        html_math = res_math.content.decode("utf-8")
        self.assertIn("Тестовая часть (1-12)", html_math)
