from django.test import SimpleTestCase

from core.sdamgia_latex import latex_from_sdamgia_alt


class SdamgiaLatexTests(SimpleTestCase):
    def test_fraction_and_parentheses(self):
        alt = (
            "18 умножить на левая круглая скобка дробь: числитель: 1, знаменатель: 9 конец дроби "
            "правая круглая скобка в квадрате минус 20 умножить на дробь: числитель: 1, знаменатель: 9 конец дроби ."
        )
        latex = latex_from_sdamgia_alt(alt)
        self.assertIsNotNone(latex)
        self.assertEqual(latex.replace(" ", ""), r"18\cdot(\frac{1}{9})^2-20\cdot\frac{1}{9}".replace(" ", ""))

    def test_mixed_number(self):
        alt = "целаячасть : 6, дробнаячасть : числитель : 1, знаменатель : 2"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex, r"\frac{13}{2}")

    def test_decimal_fraction_tokens(self):
        alt = "дробь : числитель : 4, 8 · 0, 4, знаменатель : 0, 6конецдроби"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), r"\frac{4,8\cdot0,4}{0,6}".replace(" ", ""))

    def test_join_digits_in_denominator(self):
        alt = "дробь: числитель: 1, знаменатель: 3 0 конец дроби"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex, r"\frac{1}{30}")

    def test_compact_tfrac(self):
        alt = "дробь: числитель: 1, знаменатель: \\tfrac130 плюс \\tfrac142 конец дроби"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), r"\frac{1}{\frac{1}{30}+\frac{1}{42}}".replace(" ", ""))

    def test_inequality_words(self):
        alt = "a плюс 4 больше 0"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), "a+4>0")

    def test_sqrt_tokens(self):
        alt = "корень из: начало аргумента: 42 конец аргумента"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex, r"\sqrt{42}")

    def test_power_words(self):
        alt = "(3 \\cdot 10) степени 8"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), r"(3\cdot10)^{8}".replace(" ", ""))

    def test_sanitize_left_right_mismatch(self):
        alt = "\\left( 1 плюс 2"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), "(1+2")

    def test_power_attached_and_negative(self):
        alt = "aстепени (8) · aстепени (17): aстепени (20) · 4степени(-10)"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(
            latex.replace(" ", ""),
            r"a^{8}\cdota^{17}:a^{20}\cdot4^{-10}".replace(" ", ""),
        )

    def test_v_stepeni_and_sqrt_fallback(self):
        alt = (
            "дробь: числитель: корень из: начало аргумента: 25a в степени левая круглая скобка 9 конец аргумента "
            "правая круглая скобка умножить на корень из: начало аргумента: 16b в степени левая круглая скобка 8 конец "
            "аргумента правая круглая скобка , знаменатель: корень из: начало аргумента: a в степени левая круглая скобка "
            "5 конец аргумента b в степени левая круглая скобка 8 правая круглая скобка правая круглая скобка конец дроби"
        )
        latex = latex_from_sdamgia_alt(alt)
        self.assertIsNotNone(latex)
        self.assertIn(r"\sqrt{25a^{9}}", latex)
        self.assertIn(r"\sqrt{16b^{8}}", latex)
        self.assertIn(r"\sqrt{a^{5}b^{8}}", latex.replace(" ", ""))

    def test_removes_stray_v_before_power(self):
        alt = "4в^{-10}\\cdot (4^3)в^4"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), r"4^{-10}\cdot(4^3)^4".replace(" ", ""))

    def test_fix_broken_frac_extra_brace(self):
        alt = "\\sqrt{\\frac{36a^{21}}}{a^{15}}}"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), r"\sqrt{\frac{36a^{21}}{a^{15}}}".replace(" ", ""))

    def test_balances_missing_braces(self):
        alt = "\\sqrt{\\frac{36a^{21}}{a^{15}}"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), r"\sqrt{\frac{36a^{21}}{a^{15}}}".replace(" ", ""))

    def test_degrees_word_converts_to_circ(self):
        alt = "26градусов"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), r"26^{\circ}".replace(" ", ""))

    def test_sqrt_plain_wording_converts(self):
        alt = "кореньиз3"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), r"\sqrt{3}".replace(" ", ""))

    def test_sqrt_plain_in_expression(self):
        alt = "12кореньиз3"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), r"12\sqrt{3}".replace(" ", ""))

    def test_trig_words_converts(self):
        alt = "синусA=0,4"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), r"\sin A=0,4".replace(" ", ""))

    def test_infinity_word_converts(self):
        alt = "(-3; +бесконечность)"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), r"(-3;\infty)".replace(" ", ""))

    def test_infinity_symbol_converts(self):
        alt = "(-3; ∞)"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), r"(-3;\infty)".replace(" ", ""))

    def test_negative_infinity_symbol_converts(self):
        alt = "(-∞; -3)"
        latex = latex_from_sdamgia_alt(alt)
        self.assertEqual(latex.replace(" ", ""), r"(-\infty;-3)".replace(" ", ""))

    def test_degrees_word_hyphenation_cleanup(self):
        alt = "Ответ дайте в гра- дусах."
        latex = latex_from_sdamgia_alt(alt)
        self.assertIn("градусах", latex.lower())
        self.assertNotIn("гра-", latex.lower())

    def test_degrees_word_hyphenation_cleanup_grad_u_dash(self):
        alt = "Ответ дайте в граду- сах."
        latex = latex_from_sdamgia_alt(alt)
        self.assertIn("градусах", latex.lower())
        self.assertNotIn("граду-", latex.lower())
