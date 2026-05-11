from django.test import SimpleTestCase


class SdamgiaSoftHyphenCleanupTests(SimpleTestCase):
    def test_normalize_sdamgia_html_removes_soft_hyphen_in_text_and_alt(self):
        from core.services_reshuege import normalize_sdamgia_html

        html = '<div>гра\u00adду\u00adсов <img alt="48 гра\u00adду\u00adсов" src="/x.svg"></div>'
        out = normalize_sdamgia_html(html)
        self.assertNotIn("\u00ad", out)
        self.assertIn("градусов", out)

