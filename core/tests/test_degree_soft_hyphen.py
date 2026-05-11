from django.test import SimpleTestCase

from core.tex_replace import fix_latex_tokens_in_html, fix_math_words_in_html


class DegreeSoftHyphenTests(SimpleTestCase):
    def test_degree_word_with_soft_hyphen_in_plain_text(self):
        html = "<p>48\u00adградусов</p>"
        out, _ = fix_math_words_in_html(html)
        self.assertIn(r"$48^{\circ}$", out)
        self.assertNotIn("градусов", out)

    def test_degree_word_with_soft_hyphen_inside_math(self):
        html = "<p>$\\angle BAC = 48\u00adградусов$</p>"
        out, _ = fix_latex_tokens_in_html(html)
        self.assertIn(r"48^{\circ}", out)
        self.assertNotIn("градусов", out)

