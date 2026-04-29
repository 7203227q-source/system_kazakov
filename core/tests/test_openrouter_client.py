import os

from django.test import SimpleTestCase


class OpenRouterClientTests(SimpleTestCase):
    def test_generate_task_regeneration_parses_response(self):
        os.environ["OPENROUTER_API_KEY"] = "test"
        os.environ["OPENROUTER_APP_NAME"] = "Система Казакова"

        try:
            from unittest.mock import patch
            from core.openrouter_client import generate_task_regeneration
        except Exception as e:
            self.fail(f"Missing OpenRouter client: {e}")

        class DummyTask:
            correct_answer = "1"

            def get_content_for_theme(self, theme="classic"):
                return "<p>Old</p>"

            def get_solution_for_theme(self, theme="classic"):
                return "<p>Sol</p>"

            id = 1

        dummy_response = {
            "choices": [
                {
                    "message": {
                        "content": '{"content_html":"<p>NEW</p>","solution_html":"<p>NEW_SOL</p>","correct_answer":"2","notes":""}'
                    }
                }
            ]
        }

        import core.openrouter_client as oc
        if not hasattr(oc, "requests"):
            self.fail("OpenRouter client must use requests to perform HTTP calls")

        with patch("core.openrouter_client.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response
            result = generate_task_regeneration(task=DummyTask(), mode="full", model="test", prompt_template="x")

        self.assertEqual(result["correct_answer"], "2")
        self.assertIn("NEW", result["content_html"])
