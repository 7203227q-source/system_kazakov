from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, StudentSubjectProfile, Subject, User


class StudentDashboardSubjectIdParsingTests(TestCase):
    def test_dashboard_ignores_invalid_subject_id(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        fmt = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=True)
        StudentSubjectProfile.objects.create(student=student, subject=subject, target_score=80, exam_format=fmt)

        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_dashboard") + "?subject_id=abc")
        self.assertEqual(res.status_code, 200)

