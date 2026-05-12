import re

from django.test import TestCase
from django.urls import reverse

from core.models import User


class ChatUnreadBadgeTests(TestCase):
    def test_tutor_sidebar_contains_unread_count_polling(self):
        tutor = User.objects.create(username="t", role="tutor")
        self.client.force_login(tutor)
        res = self.client.get(reverse("tutor_dashboard"))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")
        self.assertIn(reverse("api_unread_count"), html)
        self.assertIn("fetch(", html)

    def test_student_sidebar_contains_unread_count_polling(self):
        student = User.objects.create(username="s", role="student")
        self.client.force_login(student)
        res = self.client.get(reverse("student_dashboard"))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")
        self.assertIn(reverse("api_unread_count"), html)
        self.assertIn("fetch(", html)
