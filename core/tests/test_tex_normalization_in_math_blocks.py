from django.test import TestCase

from core.views import normalize_tex_in_feedback


class TexNormalizationInMathBlocksTests(TestCase):
    def test_normalizes_fracpi_and_trig_inside_display_math(self):
        src = "$$cos(fracpi2+2x)=-sin(2x)$$"
        out = normalize_tex_in_feedback(src)
        self.assertIn("$$\\cos(\\frac{\\pi}{2}+2x)=-\\sin(2x)$$", out)

