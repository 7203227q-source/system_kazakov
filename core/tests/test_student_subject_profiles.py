from django.test import TestCase
from django.urls import reverse

from core.models import User


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
