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

    def test_renders_with_management_key_and_aggregates_by_model(self):
        os.environ["OPENROUTER_API_KEY"] = "test"
        os.environ["OPENROUTER_MANAGEMENT_KEY"] = "mtest"

        class Resp:
            def __init__(self, payload):
                self.status_code = 200
                self._payload = payload
                self.text = "ok"

            def json(self):
                return self._payload

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/key"):
                return Resp({"data": {"label": "k", "limit": None, "limit_remaining": None, "usage": 1, "usage_daily": 1, "usage_weekly": 1, "usage_monthly": 1}})
            if url.endswith("/credits"):
                return Resp({"data": {"total_credits": 100.0, "total_usage": 25.0}})
            if url.endswith("/activity"):
                return Resp({"data": [
                    {"model": "m1", "usage": 1.5, "requests": 2},
                    {"model": "m1", "usage": 0.5, "requests": 1},
                    {"model": "m2", "usage": 3.0, "requests": 4},
                ]})
            raise AssertionError(f"Unexpected URL {url}")

        with patch("core.views.requests.get", side_effect=fake_get):
            self.client.force_login(self.admin)
            res = self.client.get(reverse("admin_openrouter_balance"))

        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "m2")
        self.assertContains(res, "3.000000")
        self.assertContains(res, "m1")
        self.assertContains(res, "2.000000")
