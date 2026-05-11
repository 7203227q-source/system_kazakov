from unittest.mock import Mock, patch

from django.test import TestCase

from core.utils import download_and_replace_images


class DownloadAndReplaceImagesSegmentTests(TestCase):
    def test_does_not_collide_between_content_and_solution(self):
        html = '<p><img src="https://math-oge.sdamgia.ru/get_file?id=1"></p>'

        mocked = Mock()
        mocked.status_code = 200
        mocked.headers = {"Content-Type": "image/svg+xml"}
        mocked.content = b"<svg></svg>"

        with patch("requests.get", return_value=mocked), patch("core.utils.default_storage") as storage:
            storage.exists.return_value = False
            storage.save.side_effect = lambda filename, content: filename

            content_out = download_and_replace_images(html, "314127", "classic", base_url="https://math-oge.sdamgia.ru", segment="content")
            solution_out = download_and_replace_images(html, "314127", "classic", base_url="https://math-oge.sdamgia.ru", segment="solution")

        self.assertIn("/media/tasks/314127_classic_content_0.svg", content_out)
        self.assertIn("/media/tasks/314127_classic_solution_0.svg", solution_out)

    def test_uses_image_host_as_referer(self):
        html = '<p><img src="https://oge.sdamgia.ru/formula/svg/x.svg"></p>'

        mocked = Mock()
        mocked.status_code = 200
        mocked.headers = {"Content-Type": "image/svg+xml"}
        mocked.content = b"<svg></svg>"

        captured = {}

        def fake_get(url, headers=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            return mocked

        with patch("requests.get", side_effect=fake_get), patch("core.utils.default_storage") as storage:
            storage.exists.return_value = False
            storage.save.side_effect = lambda filename, content: filename
            download_and_replace_images(html, "314127", "classic", base_url="https://math-oge.sdamgia.ru", segment="content")

        self.assertEqual(captured.get("url"), "https://oge.sdamgia.ru/formula/svg/x.svg")
        self.assertEqual(captured.get("headers", {}).get("Referer"), "https://oge.sdamgia.ru/")
