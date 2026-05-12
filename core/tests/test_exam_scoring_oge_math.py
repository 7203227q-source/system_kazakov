from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.exam_scoring import grade_from_primary, primary_from_percent, estimate_geometry_primary
from core.models import DailySnapshot, ExamFormat, ExamScoreScale, Subject, StudentSubjectProfile, TaskType, User


class OgeMathExamScoringTests(TestCase):
    def test_primary_from_percent(self):
        self.assertEqual(primary_from_percent(0, 31), 0)
        self.assertEqual(primary_from_percent(100, 31), 31)
        self.assertEqual(primary_from_percent(50, 31), 16)  # round(15.5) -> 16

    def test_grade_thresholds_with_geometry_requirement(self):
        rules = [
            {"grade": 2, "min_total": 0, "max_total": 7, "min_geometry": None},
            {"grade": 3, "min_total": 8, "max_total": 14, "min_geometry": 2},
            {"grade": 4, "min_total": 15, "max_total": 21, "min_geometry": 2},
            {"grade": 5, "min_total": 22, "max_total": 31, "min_geometry": 2},
        ]

        # по сумме тянет на 3, но геометрии нет => 2
        self.assertEqual(grade_from_primary(10, geometry_primary=1, grade_rules=rules), 2)

        # по сумме 2 => 2 независимо от геометрии
        self.assertEqual(grade_from_primary(5, geometry_primary=0, grade_rules=rules), 2)

        # тянет на 4 и геометрия выполнена
        self.assertEqual(grade_from_primary(18, geometry_primary=2, grade_rules=rules), 4)

    def test_estimate_geometry_primary_by_share(self):
        # если геометрия ~ 1/3 экзамена, то при 18 баллах ожидаем ~6
        self.assertEqual(estimate_geometry_primary(total_primary=18, geometry_share=1 / 3), 6)


class OgeMathDashboardDisplayTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ математика", year=2025, is_active=True)
        ExamScoreScale.objects.create(
            exam_format=self.ef,
            max_primary_score=31,
            grade_rules=[
                {"grade": 2, "min_total": 0, "max_total": 7, "min_geometry": None},
                {"grade": 3, "min_total": 8, "max_total": 14, "min_geometry": 2},
                {"grade": 4, "min_total": 15, "max_total": 21, "min_geometry": 2},
                {"grade": 5, "min_total": 22, "max_total": 31, "min_geometry": 2},
            ],
        )

        # для доли геометрии: всего 1 + 2 = 3, гео 2 => share 2/3
        TaskType.objects.create(exam_format=self.ef, number=1, name="N1", max_points=1, is_geometry=False)
        TaskType.objects.create(exam_format=self.ef, number=15, name="Геометрия", max_points=2, is_geometry=True)

        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        self.profile = StudentSubjectProfile.objects.create(
            student=self.student,
            subject=self.subject,
            exam_format=self.ef,
            trust_factor=0.6,
            learning_velocity=1.0,
        )

        today = timezone.localdate()
        DailySnapshot.objects.create(
            student=self.student,
            subject=self.subject,
            date=today,
            current_mastery=50.0,  # => 16/31 => оценка 4
            predicted_exam_score=80.0,  # => 25/31 => оценка 5
        )

    def test_student_dashboard_shows_points_and_grade(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_dashboard"), {"subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "16/31")
        self.assertContains(res, "оценка 4")
        self.assertContains(res, "25/31")
        self.assertContains(res, "оценка 5")

    def test_tutor_dashboard_shows_points_and_grade(self):
        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"), {"student_id": self.student.id, "subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "25/31")
        self.assertContains(res, "оценка 5")
