import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, StudentSubjectProfile, Subject, User


class TutorStudentExamSettingsTests(TestCase):
    def test_tutor_can_update_student_exam_settings(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subject = Subject.objects.create(name="Математика")
        fmt = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=True)
        p = StudentSubjectProfile.objects.create(student=student, subject=subject, target_score=80, level=1, xp=0)

        self.client.login(username="t", password="pass")
        exam_date = (timezone.now().date() + datetime.timedelta(days=10)).isoformat()
        res = self.client.post(
            reverse("tutor_update_student_exam_settings", args=[student.id]),
            {"subject_id": str(subject.id), "exam_format_id": str(fmt.id), "exam_date": exam_date},
        )
        self.assertEqual(res.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.exam_format_id, fmt.id)
        self.assertEqual(p.exam_date.isoformat(), exam_date)

