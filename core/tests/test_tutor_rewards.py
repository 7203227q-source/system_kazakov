from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, StudentSubjectProfile, User


class TutorRewardsTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.other_tutor = User.objects.create_user(username="t2", password="pass", role="tutor")
        self.tutor.students.add(self.student)
        self.subject = Subject.objects.create(name="Математика")
        ExamFormat.objects.create(subject=self.subject, name="ОГЭ математика", year=2026, is_active=True)
        self.profile = StudentSubjectProfile.objects.create(student=self.student, subject=self.subject, xp=0, level=1, target_score=80)

    def test_tutor_can_award_xp_to_student_subject(self):
        self.client.login(username="t", password="pass")
        res = self.client.post(
            reverse("tutor_award_xp"),
            {"student_id": str(self.student.id), "subject_id": str(self.subject.id), "xp_amount": "50", "reason": "Молодец"},
        )
        self.assertEqual(res.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.xp, 50)
        self.assertEqual(self.profile.level, 1)
        from core.models import TutorReward

        self.assertEqual(TutorReward.objects.count(), 1)

    def test_other_tutor_cannot_award(self):
        self.client.login(username="t2", password="pass")
        res = self.client.post(reverse("tutor_award_xp"), {"student_id": str(self.student.id), "subject_id": str(self.subject.id), "xp_amount": "50"})
        self.assertEqual(res.status_code, 403)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.xp, 0)

