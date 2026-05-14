from django.test import TestCase


class AIFeedbackGreekAndFracExprTests(TestCase):
    def test_greek_words_and_frac_expr_are_normalized(self):
        from core.views import normalize_tex_in_feedback

        out = normalize_tex_in_feedback("A23 = fracnuR(T3-T2)1 - gamma")
        self.assertIn("\\frac{\\nu R(T3-T2)}{1}", out)
        self.assertIn("\\gamma", out)

