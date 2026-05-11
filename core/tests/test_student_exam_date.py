from django.test import TestCase

from core.models import StudentSubjectProfile, Subject, User


class StudentExamDateModelTests(TestCase):
    def test_profile_has_exam_date(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        p = StudentSubjectProfile.objects.create(student=student, subject=subject, target_score=80, level=1, xp=0)
        self.assertTrue(hasattr(p, "exam_date"))


class StudentExamDateEndpointTests(TestCase):
    def test_student_can_update_exam_date(self):
        import datetime

        from django.urls import reverse
        from django.utils import timezone

        from core.models import ExamFormat

        student = User.objects.create_user(username="s", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        fmt = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=True)
        p = StudentSubjectProfile.objects.create(student=student, subject=subject, target_score=80, level=1, xp=0, exam_format=fmt)

        self.client.login(username="s", password="pass")
        exam_date = (timezone.now().date() + datetime.timedelta(days=30)).isoformat()
        res = self.client.post(
            reverse("student_update_exam_date"),
            {"subject_id": str(subject.id), "exam_date": exam_date},
        )
        self.assertEqual(res.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.exam_date.isoformat(), exam_date)
