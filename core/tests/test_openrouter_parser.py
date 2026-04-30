from django.test import SimpleTestCase


class OpenRouterParserTests(SimpleTestCase):
    def test_parse_openrouter_json(self):
        try:
            from core.services_openrouter import parse_openrouter_json
        except Exception as e:
            self.fail(f"Missing parse_openrouter_json: {e}")

        text = '{"content_html":"<p>Hi</p>","solution_html":"<p>Sol</p>","correct_answer":"42","notes":"ok"}'
        parsed = parse_openrouter_json(text)
        self.assertEqual(parsed["correct_answer"], "42")
        self.assertIn("<p>Hi</p>", parsed["content_html"])

