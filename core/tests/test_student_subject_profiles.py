from django.test import TestCase
from django.urls import reverse

from core.models import StudentSubjectProfile, Subject, User


class StudentLearningSettingsPageTests(TestCase):
    def test_student_can_open_learning_settings_page(self):
        student = User.objects.create(username="s", role="student")
        self.client.force_login(student)
        res = self.client.get(reverse("student_learning_settings"))
        self.assertEqual(res.status_code, 200)


class StudentSidebarLearningSettingsLinkTests(TestCase):
    def test_student_sidebar_has_learning_settings_link(self):
        student = User.objects.create(username="s", role="student")
        self.client.force_login(student)
        res = self.client.get(reverse("student_dashboard"))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")
        self.assertIn(reverse("student_learning_settings"), html)


class StudentSubjectProfileCreateTests(TestCase):
    def setUp(self):
        self.student = User.objects.create(username="s", role="student")
        self.subject1 = Subject.objects.create(name="Математика")
        self.subject2 = Subject.objects.create(name="Физика")
        StudentSubjectProfile.objects.create(student=self.student, subject=self.subject1)

    def test_student_can_add_second_subject_profile(self):
        self.client.force_login(self.student)
        res = self.client.post(reverse("student_add_subject_profile"), {"subject_id": self.subject2.id})
        self.assertEqual(res.status_code, 302)
        self.assertTrue(StudentSubjectProfile.objects.filter(student=self.student, subject=self.subject2).exists())


class StudentDashboardIsCompactTests(TestCase):
    def test_dashboard_does_not_show_exam_forms(self):
        student = User.objects.create(username="s", role="student")
        subject = Subject.objects.create(name="Математика")
        StudentSubjectProfile.objects.create(student=student, subject=subject)
        self.client.force_login(student)
        res = self.client.get(reverse("student_dashboard"))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")
        self.assertNotIn(reverse("student_update_exam_format"), html)
        self.assertNotIn(reverse("student_update_exam_date"), html)


class StudentTargetScoreUpdateTests(TestCase):
    def test_student_can_update_target_score_for_active_subject(self):
        student = User.objects.create(username="s", role="student")
        subject = Subject.objects.create(name="Математика")
        profile = StudentSubjectProfile.objects.create(student=student, subject=subject, target_score=80)
        self.client.force_login(student)
        res = self.client.post(
            reverse("student_update_target_score"),
            {"subject_id": subject.id, "target_score": "90"},
        )
        self.assertEqual(res.status_code, 302)
        profile.refresh_from_db()
        self.assertEqual(profile.target_score, 90)
