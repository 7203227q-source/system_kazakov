import os

from django.test import SimpleTestCase


class OpenRouterApiKeyValidationTests(SimpleTestCase):
    def test_non_ascii_api_key_raises(self):
        os.environ["OPENROUTER_API_KEY"] = "ключ"
        try:
            from core.openrouter_models import fetch_openrouter_models
        except Exception as e:
            self.fail(f"Missing openrouter_models: {e}")

        with self.assertRaises(ValueError):
            fetch_openrouter_models()

