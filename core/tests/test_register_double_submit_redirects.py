from django.test import TestCase
from django.urls import reverse

from core.models import User


class RegisterDoubleSubmitRedirectsTests(TestCase):
    def test_second_submit_redirects_to_select_role_when_user_already_logged_in(self):
        url = reverse("register")
        payload = {
            "first_name": "Иван",
            "last_name": "Иванов",
            "email": "s@example.com",
            "password": "pass12345",
            "password_confirm": "pass12345",
        }

        r1 = self.client.post(url, payload)
        self.assertEqual(r1.status_code, 302)
        self.assertEqual(r1.url, reverse("select_role"))

        # user should be authenticated after the first submit
        u = User.objects.get(username="s@example.com")
        self.assertEqual(u.role, "unassigned")

        r2 = self.client.post(url, payload)
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(r2.url, reverse("select_role"))

