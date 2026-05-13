import os
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.models import User


class AdminOpenRouterBalanceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="a", password="pass", role="admin")
        self.student = User.objects.create_user(username="s", password="pass", role="student")

    def test_requires_admin(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("admin_openrouter_balance"))
        self.assertIn(res.status_code, (302, 403))

    def test_renders_without_management_key(self):
        os.environ["OPENROUTER_API_KEY"] = "test"
        os.environ.pop("OPENROUTER_MANAGEMENT_KEY", None)

        with patch("core.views.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = {
                "data": {
                    "label": "k",
                    "limit": None,
                    "limit_remaining": None,
                    "usage": 1,
                    "usage_daily": 1,
                    "usage_weekly": 1,
                    "usage_monthly": 1,
                }
            }

            self.client.force_login(self.admin)
            res = self.client.get(reverse("admin_openrouter_balance"))

        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "OPENROUTER_MANAGEMENT_KEY")

