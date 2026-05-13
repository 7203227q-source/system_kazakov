from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bs4 import BeautifulSoup

from core.models import DailySnapshot, ExamFormat, StudentSubjectProfile, Subject, TaskType, User


class TutorDashboardTaskTypeRatesTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        self.subj = Subject.objects.create(name="Математика")
        self.ef_empty = ExamFormat.objects.create(subject=self.subj, name="ОГЭ математика", year=2026, is_active=True)
        self.ef_with_types = ExamFormat.objects.create(subject=self.subj, name="ОГЭ математика", year=2025, is_active=False)
        for n in range(1, 6):
            TaskType.objects.create(exam_format=self.ef_with_types, number=n, name=f"Тип {n}", max_points=1)

        StudentSubjectProfile.objects.create(student=self.student, subject=self.subj, exam_format=self.ef_empty)
        DailySnapshot.objects.create(student=self.student, subject=self.subj, date=timezone.localdate(), current_mastery=10, predicted_exam_score=10)

    def test_tutor_dashboard_does_not_show_fake_numbers_when_no_tasktypes(self):
        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"), {"student_id": self.student.id, "subject_id": self.subj.id})
        self.assertEqual(res.status_code, 200)
        soup = BeautifulSoup(res.content, "html.parser")
        tiles = soup.select(".task-type-tile")
        self.assertEqual(len(tiles), 0)
