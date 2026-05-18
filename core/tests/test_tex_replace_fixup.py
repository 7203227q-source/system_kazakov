from django.test import SimpleTestCase

from core.tex_replace import fix_latex_tokens_in_html


class TexReplaceFixupTests(SimpleTestCase):
    def test_fixes_mixed_number_inside_math(self):
        html = "<p>$целаячасть : 6, дробнаячасть : числитель : 1, знаменатель : 2 - \\frac{47}{10}$</p>"
        out, fixed = fix_latex_tokens_in_html(html)
        self.assertEqual(fixed, 1)
        self.assertIn(r"$\frac{13}{2}-\frac{47}{10}$", out.replace(" ", ""))

    def test_fixes_compact_tfrac_inside_math(self):
        html = "<p>$\\tfrac130+\\tfrac142$</p>"
        out, fixed = fix_latex_tokens_in_html(html)
        self.assertEqual(fixed, 1)
        self.assertIn(r"$\frac{1}{30}+\frac{1}{42}$", out.replace(" ", ""))

    def test_fixes_power_words_inside_math(self):
        html = "<p>$(3\\cdot10)степени8$</p>"
        out, fixed = fix_latex_tokens_in_html(html)
        self.assertEqual(fixed, 1)
        self.assertIn(r"$(3\cdot10)^{8}$", out.replace(" ", ""))

    def test_fixes_inside_paren_delimiters(self):
        html = "<p>\\\\(\\\\sqrt{\\\\frac{36a^{21}}}{a^{15}}}\\\\)</p>"
        out, fixed = fix_latex_tokens_in_html(html)
        self.assertGreaterEqual(fixed, 1)
        self.assertIn(r"\\(\\sqrt{\\frac{36a^{21}}{a^{15}}}\\)", out.replace(" ", ""))

    def test_converts_russian_trig_and_greek_words_inside_math(self):
        html = "<p>$S=\\frac{d_1 d_2 синус альфа}{2}$</p>"
        out, fixed = fix_latex_tokens_in_html(html)
        self.assertGreaterEqual(fixed, 1)
        self.assertIn(r"\sin", out)
        self.assertIn(r"\alpha", out)
        self.assertNotIn("синус", out.lower())
        self.assertNotIn("альфа", out.lower())

    def test_converts_infinity_word_inside_math(self):
        html = "<p>$(-3; +бесконечность)$</p><p>$(-бесконечность; -3)$</p>"
        out, fixed = fix_latex_tokens_in_html(html)
        self.assertGreaterEqual(fixed, 1)
        self.assertIn(r"\infty", out)
        self.assertNotIn("бесконечност", out.lower())
