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
