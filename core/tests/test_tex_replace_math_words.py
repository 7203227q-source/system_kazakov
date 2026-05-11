from django.test import SimpleTestCase


class TexReplaceMathWordsTests(SimpleTestCase):
    def test_converts_trig_words_in_plain_html(self):
        from core.tex_replace import fix_math_words_in_html

        html = "<p>BC = 8, синусA = 0,4. Найдите AB.</p>"
        out, changed = fix_math_words_in_html(html)
        self.assertGreater(changed, 0)
        self.assertIn(r"$\sin A$", out)

    def test_converts_degrees_word_in_plain_html(self):
        from core.tex_replace import fix_math_words_in_html

        html = "<p>∠BAC = 48градусов.</p>"
        out, changed = fix_math_words_in_html(html)
        self.assertGreater(changed, 0)
        self.assertIn(r"$48^{\circ}$", out)

    def test_converts_infinity_word_in_plain_html(self):
        from core.tex_replace import fix_math_words_in_html

        html = "<p>(-3; +бесконечность)</p><p>(-бесконечность; -3)</p>"
        out, changed = fix_math_words_in_html(html)
        self.assertGreater(changed, 0)
        self.assertIn(r"$\infty$", out)
        self.assertIn(r"$-\infty$", out)

    def test_fix_hyphenation_in_degrees_word(self):
        from core.tex_replace import fix_math_words_in_html

        html = "<p>Ответ дайте в гра- дусах.</p>"
        out, _changed = fix_math_words_in_html(html)
        self.assertIn("градусах", out.lower())
        self.assertNotIn("гра-", out.lower())

    def test_fix_hyphenation_in_degrees_word_grad_u_dash(self):
        from core.tex_replace import fix_math_words_in_html

        html = "<p>Ответ дайте в граду- сах.</p>"
        out, _changed = fix_math_words_in_html(html)
        self.assertIn("градусах", out.lower())
        self.assertNotIn("граду-", out.lower())
