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
        self.assertEqual(latex.replace(" ", ""), r"18\cdot\left(\frac{1}{9}\right)^2-20\cdot\frac{1}{9}".replace(" ", ""))

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
