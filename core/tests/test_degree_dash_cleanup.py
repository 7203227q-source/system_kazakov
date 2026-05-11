from django.test import SimpleTestCase

from core.sdamgia_latex import latex_from_sdamgia_alt


class DegreeDashCleanupTests(SimpleTestCase):
    def test_degree_word_cleanup_does_not_leave_dash(self):
        alt = "Ответ дайте в - градусов"
        latex = latex_from_sdamgia_alt(alt)
        self.assertNotIn("- градусов", latex)

