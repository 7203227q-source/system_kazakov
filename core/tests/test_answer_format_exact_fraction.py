from django.test import TestCase


class ExactFractionToDecimalStrTests(TestCase):
    def test_terminating_decimal(self):
        from core.answer_format import exact_fraction_to_decimal_str

        self.assertEqual(exact_fraction_to_decimal_str("7/40"), "0.175")

    def test_reduces_fraction(self):
        from core.answer_format import exact_fraction_to_decimal_str

        self.assertEqual(exact_fraction_to_decimal_str("10/4"), "2.5")

    def test_integer(self):
        from core.answer_format import exact_fraction_to_decimal_str

        self.assertEqual(exact_fraction_to_decimal_str("123/1"), "123")

    def test_negative(self):
        from core.answer_format import exact_fraction_to_decimal_str

        self.assertEqual(exact_fraction_to_decimal_str("-7/40"), "-0.175")

    def test_non_terminating_rejected(self):
        from core.answer_format import exact_fraction_to_decimal_str

        with self.assertRaises(ValueError):
            exact_fraction_to_decimal_str("1/3")


class ExtractExactFractionTests(TestCase):
    def test_extract_exact_fraction(self):
        from core.answer_format import extract_exact_fraction

        self.assertEqual(extract_exact_fraction("foo exact_fraction=7/40 bar"), "7/40")

