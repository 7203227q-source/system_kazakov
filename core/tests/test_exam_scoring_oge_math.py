from django.test import TestCase

from core.exam_scoring import grade_from_primary, primary_from_percent, estimate_geometry_primary


class OgeMathExamScoringTests(TestCase):
    def test_primary_from_percent(self):
        self.assertEqual(primary_from_percent(0, 31), 0)
        self.assertEqual(primary_from_percent(100, 31), 31)
        self.assertEqual(primary_from_percent(50, 31), 16)  # round(15.5) -> 16

    def test_grade_thresholds_with_geometry_requirement(self):
        rules = [
            {"grade": 2, "min_total": 0, "max_total": 7, "min_geometry": None},
            {"grade": 3, "min_total": 8, "max_total": 14, "min_geometry": 2},
            {"grade": 4, "min_total": 15, "max_total": 21, "min_geometry": 2},
            {"grade": 5, "min_total": 22, "max_total": 31, "min_geometry": 2},
        ]

        # по сумме тянет на 3, но геометрии нет => 2
        self.assertEqual(grade_from_primary(10, geometry_primary=1, grade_rules=rules), 2)

        # по сумме 2 => 2 независимо от геометрии
        self.assertEqual(grade_from_primary(5, geometry_primary=0, grade_rules=rules), 2)

        # тянет на 4 и геометрия выполнена
        self.assertEqual(grade_from_primary(18, geometry_primary=2, grade_rules=rules), 4)

    def test_estimate_geometry_primary_by_share(self):
        # если геометрия ~ 1/3 экзамена, то при 18 баллах ожидаем ~6
        self.assertEqual(estimate_geometry_primary(total_primary=18, geometry_share=1 / 3), 6)

