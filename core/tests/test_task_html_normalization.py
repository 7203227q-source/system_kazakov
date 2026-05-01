from django.test import SimpleTestCase


class NormalizeTaskHtmlTests(SimpleTestCase):
    def test_leaves_small_number_of_br_intact(self):
        from core.task_html import normalize_task_html

        html = "<p>а) Докажите, что ...<br>б) Найдите ...</p>"
        self.assertEqual(normalize_task_html(html), html)

    def test_collapses_many_br_into_spaces_in_plain_paragraph(self):
        from core.task_html import normalize_task_html

        html = "<p>Высоты<br>BB₁<br>и<br>CC₁<br>остроугольного<br>треугольника<br>ABC<br>пересекаются<br>в точке<br>H.</p>"
        out = normalize_task_html(html)
        self.assertIn(
            "Высоты BB₁ и CC₁ остроугольного треугольника ABC пересекаются в точке H.",
            out,
        )
        self.assertNotIn("<br", out)

    def test_does_not_touch_lists_and_tables(self):
        from core.task_html import normalize_task_html

        html = "<ul><li>А</li><li>Б</li></ul><table><tr><td>1</td></tr></table>"
        self.assertEqual(normalize_task_html(html), html)
