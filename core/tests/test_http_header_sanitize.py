from django.test import SimpleTestCase


class HttpHeaderSanitizeTests(SimpleTestCase):
    def test_sanitize_header_value_removes_non_ascii(self):
        try:
            from core.http_headers import sanitize_header_value
        except Exception as e:
            self.fail(f"Missing sanitize_header_value: {e}")

        self.assertEqual(sanitize_header_value("Система Казакова"), " ")
        self.assertEqual(sanitize_header_value("kazakov-system"), "kazakov-system")

