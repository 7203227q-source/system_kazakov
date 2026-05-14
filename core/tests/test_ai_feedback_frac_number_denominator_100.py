from django.test import TestCase


class AIFeedbackFracNumberDenominator100Tests(TestCase):
    def test_frac40100_is_normalized_to_latex_frac(self):
        from core.views import normalize_tex_in_feedback

        out = normalize_tex_in_feedback("frac40100x + frac48100y = frac42100(x+y)")
        self.assertIn("\\frac{40}{100}", out)
        self.assertIn("\\frac{48}{100}", out)
        self.assertIn("\\frac{42}{100}", out)
        self.assertNotIn("frac40100", out)
