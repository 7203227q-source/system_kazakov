from django.test import TestCase
from django.urls import reverse

from core.models import Subject, User, StudentSubjectProfile, TutorReward


class StudentDashboardRewardsTests(TestCase):
    def test_student_sees_own_rewards_with_reason(self):
        subject = Subject.objects.create(name="Математика")
        tutor = User.objects.create_user(username="t1", password="pw", role="tutor")
        student = User.objects.create_user(username="s1", password="pw", role="student")
        other_student = User.objects.create_user(username="s2", password="pw", role="student")

        StudentSubjectProfile.objects.create(student=student, subject=subject, xp=0, level=1)
        StudentSubjectProfile.objects.create(student=other_student, subject=subject, xp=0, level=1)

        TutorReward.objects.create(tutor=tutor, student=student, subject=subject, xp_amount=50, reason="Молодец")
        TutorReward.objects.create(tutor=tutor, student=other_student, subject=subject, xp_amount=10, reason="Не показывать")

        self.client.force_login(student)
        res = self.client.get(reverse("student_dashboard"))

        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Награды от репетитора")
        self.assertContains(res, "+50 XP")
        self.assertContains(res, "Молодец")
        self.assertNotContains(res, "Не показывать")

