from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, StudentSubjectProfile, Subject, TaskType, User


class ExamStructureBoundariesInGeneratorTests(TestCase):
    def _make_tutor_student(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)
        return tutor, student

    def test_math_oge_boundaries_use_extended_flag(self):
        tutor, student = self._make_tutor_student()
        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ", year=2026, is_active=True)
        StudentSubjectProfile.objects.create(student=student, subject=subj, exam_format=ef, xp=0, level=1, target_score=80)

        for n in range(1, 20):
            TaskType.objects.create(exam_format=ef, number=n, name=str(n), max_points=1, is_extended_answer=False)
        for n in range(20, 26):
            TaskType.objects.create(exam_format=ef, number=n, name=str(n), max_points=2, is_extended_answer=True)

        self.client.login(username="t", password="pass")
        url = reverse("tutor_create_assignment") + f"?student_id={student.id}&exam_format={ef.id}"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertIn("Тестовая часть (1-19)", html)
        self.assertIn("Развернутая часть (20-25)", html)

    def test_physics_ege_and_oge_boundaries_use_extended_flag(self):
        tutor, student = self._make_tutor_student()
        subj = Subject.objects.create(name="Физика")

        ef_ege = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        for n in range(1, 21):
            TaskType.objects.create(exam_format=ef_ege, number=n, name=str(n), max_points=1, is_extended_answer=False)
        for n in range(21, 27):
            TaskType.objects.create(exam_format=ef_ege, number=n, name=str(n), max_points=3, is_extended_answer=True)

        ef_oge = ExamFormat.objects.create(subject=subj, name="ОГЭ физика", year=2026, is_active=True)
        for n in range(1, 21):
            TaskType.objects.create(exam_format=ef_oge, number=n, name=str(n), max_points=1, is_extended_answer=False)
        for n in range(21, 25):
            TaskType.objects.create(exam_format=ef_oge, number=n, name=str(n), max_points=2, is_extended_answer=True)

        # профиль студента — любой из форматов (важно только что доступен предмет)
        StudentSubjectProfile.objects.create(student=student, subject=subj, exam_format=ef_ege, xp=0, level=1, target_score=80)

        self.client.login(username="t", password="pass")

        r1 = self.client.get(reverse("tutor_create_assignment") + f"?student_id={student.id}&exam_format={ef_ege.id}")
        self.assertEqual(r1.status_code, 200)
        html1 = r1.content.decode("utf-8")
        self.assertIn("Тестовая часть (1-20)", html1)
        self.assertIn("Развернутая часть (21-26)", html1)

        r2 = self.client.get(reverse("tutor_create_assignment") + f"?student_id={student.id}&exam_format={ef_oge.id}")
        self.assertEqual(r2.status_code, 200)
        html2 = r2.content.decode("utf-8")
        self.assertIn("Тестовая часть (1-20)", html2)
        self.assertIn("Развернутая часть (21-24)", html2)

