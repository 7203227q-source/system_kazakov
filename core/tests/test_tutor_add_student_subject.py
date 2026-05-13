from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, StudentSubjectProfile, Subject, User


class TutorAddStudentSubjectTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        self.math = Subject.objects.create(name="Математика")
        self.phys = Subject.objects.create(name="Физика")

        self.oge_math = ExamFormat.objects.create(subject=self.math, name="ОГЭ математика", year=2026, is_active=True)
        self.ege_phys = ExamFormat.objects.create(subject=self.phys, name="ЕГЭ физика", year=2026, is_active=True)

    def test_tutor_can_add_subject_profile(self):
        self.client.login(username="t", password="pass")

        self.assertFalse(StudentSubjectProfile.objects.filter(student=self.student, subject=self.phys).exists())

        res = self.client.post(
            reverse("tutor_add_student_subject", args=[self.student.id]),
            {"subject_id": str(self.phys.id)},
        )
        self.assertEqual(res.status_code, 302)

        prof = StudentSubjectProfile.objects.get(student=self.student, subject=self.phys)
        self.assertEqual(prof.exam_format_id, self.ege_phys.id)

