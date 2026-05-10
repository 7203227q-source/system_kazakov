from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse


class ProxyImageOgeHostsTests(TestCase):
    def test_allows_math_oge(self):
        mocked = Mock()
        mocked.status_code = 200
        mocked.headers = {"Content-Type": "image/svg+xml"}
        mocked.iter_content = lambda chunk_size=65536: [b"<svg></svg>"]

        with patch("requests.get", return_value=mocked):
            res = self.client.get(
                reverse("proxy_image"),
                {"url": "https://math-oge.sdamgia.ru/get_file?id=1"},
            )

        self.assertEqual(res.status_code, 200)
        self.assertIn("image/svg+xml", res.get("Content-Type", ""))

