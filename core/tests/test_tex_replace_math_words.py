from django.test import SimpleTestCase


class TexReplaceMathWordsTests(SimpleTestCase):
    def test_converts_trig_words_in_plain_html(self):
        from core.tex_replace import fix_math_words_in_html

        html = "<p>BC = 8, синусA = 0,4. Найдите AB.</p>"
        out, changed = fix_math_words_in_html(html)
        self.assertGreater(changed, 0)
        self.assertIn(r"$\sin A$", out)
        self.assertNotIn(r"\$\sin", out)
        self.assertNotIn("$$", out)

    def test_converts_cos_tan_and_angle_trig_words_in_plain_html(self):
        from core.tex_replace import fix_math_words_in_html

        html = "<p>косинусA = 5/7, тангенсA = 2. синус∠A = 4/5.</p>"
        out, changed = fix_math_words_in_html(html)
        self.assertGreater(changed, 0)
        self.assertIn(r"$\cos A$", out)
        self.assertIn(r"$\tan A$", out)
        self.assertIn(r"$\sin A$", out)
        self.assertNotIn("косинус", out.lower())
        self.assertNotIn("тангенс", out.lower())
        self.assertNotIn("синус", out.lower())
        self.assertNotIn(r"\$\cos", out)
        self.assertNotIn(r"\$\tan", out)
        self.assertNotIn(r"\$\sin", out)
        self.assertNotIn("$$", out)

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

    def test_converts_infinity_word_with_long_dashes(self):
        from core.tex_replace import fix_math_words_in_html

        html = "<p>(—бесконечность; 0)</p><p>(–бесконечность; 0)</p>"
        out, changed = fix_math_words_in_html(html)
        self.assertGreater(changed, 0)
        self.assertIn(r"$-\infty$", out)

    def test_converts_system_tokens_in_plain_html(self):
        from core.tex_replace import fix_math_words_in_html

        html = "<p>системавыраженийноваястрока5x + 13 ≤ 0, новаястрокаx + 5 ≥ 1.конецсистемы</p>"
        out, changed = fix_math_words_in_html(html)
        self.assertGreater(changed, 0)
        self.assertIn(r"$\begin{cases}", out)
        self.assertIn(r"5x+13\le0", out)
        self.assertIn(r"x+5\ge1", out)
        self.assertIn(r"\end{cases}$", out)

    def test_converts_infinity_symbol_in_plain_html(self):
        from core.tex_replace import fix_math_words_in_html

        html = "<p>(-3; ∞)</p><p>(-∞; -3)</p>"
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
