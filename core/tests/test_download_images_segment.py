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

