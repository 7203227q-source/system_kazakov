from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.models import User


class RegisterLoginRobustnessTests(TestCase):
    def test_register_redirects_to_select_role_and_is_logged_in(self):
        res = self.client.post(
            reverse("register"),
            {
                "first_name": "Иван",
                "last_name": "Иванов",
                "email": "student@example.com",
                "password": "pass12345",
                "password_confirm": "pass12345",
            },
            follow=True,
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.wsgi_request.user.is_authenticated)
        self.assertEqual(res.wsgi_request.user.username, "student@example.com")

    def test_register_does_not_500_if_auto_login_fails(self):
        with patch("core.views.login", side_effect=Exception("session error")):
            res = self.client.post(
                reverse("register"),
                {
                    "first_name": "Иван",
                    "last_name": "Иванов",
                    "email": "student2@example.com",
                    "password": "pass12345",
                    "password_confirm": "pass12345",
                },
            )
        self.assertEqual(res.status_code, 302)
        self.assertTrue(User.objects.filter(username="student2@example.com").exists())

