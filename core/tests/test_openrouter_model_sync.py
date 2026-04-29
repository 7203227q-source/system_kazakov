from django.test import TestCase


class OpenRouterModelSyncTests(TestCase):
    def test_sync_models_creates_records(self):
        try:
            from core.openrouter_models import sync_openrouter_models
            from core.models import OpenRouterModel
        except Exception as e:
            self.fail(f"Missing OpenRouter model sync pieces: {e}")

        from unittest.mock import patch
        import os
        os.environ["OPENROUTER_API_KEY"] = "test"
        os.environ["OPENROUTER_APP_NAME"] = "Система Казакова"

        payload = {
            "data": [
                {"id": "openai/gpt-4o-mini", "name": "GPT-4o mini", "architecture": {"modality": "text"}},
                {"id": "google/gemini-2.0-flash", "name": "Gemini 2.0 Flash", "architecture": {"modality": "multimodal"}},
            ]
        }

        with patch("core.openrouter_models.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = payload
            created, updated, deactivated = sync_openrouter_models()

        self.assertEqual(OpenRouterModel.objects.count(), 2)
        self.assertGreaterEqual(created, 2)
