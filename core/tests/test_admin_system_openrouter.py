import os

from django.test import TestCase
from django.urls import reverse

from core.models import Subject, User


class AdminSystemOpenRouterTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(username="admin_s", email="admin_s@example.com", password="pass", role="admin")
        Subject.objects.create(name="Математика")

    def test_admin_system_page_shows_openrouter_context(self):
        os.environ["OPENROUTER_API_KEY"] = "test"
        self.client.force_login(self.admin_user)
        res = self.client.get(reverse("admin_system"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("openrouter", res.context)
        self.assertIn("subjects", res.context)

