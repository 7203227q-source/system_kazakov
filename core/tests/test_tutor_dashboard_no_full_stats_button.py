from django.test import TestCase
from django.urls import reverse

from core.models import User


class TutorDashboardNoFullStatsButtonTests(TestCase):
    def test_tutor_dashboard_does_not_show_full_stats_button(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"))
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, "Полная статистика")
