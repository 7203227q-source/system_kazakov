from unittest.mock import patch

from django.test import TestCase

from core.models import ExamFormat, Subject, Task, TaskType, Topic
from core.services_reshuege import import_one_task_from_sdamgia


class SdamgiaImportDegreesFixTests(TestCase):
    def test_import_fixes_degrees_inside_math(self):
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        TaskType.objects.create(exam_format=exam_format, number=7, name="Тип 7", max_points=1)

        html = """
        <html><body>
          <div id="body348610">
            <p>из&shy;вест&shy;но, что $\\angle BAC=48 градус&shy;ов,$ <i>AD</i> — бис&shy;сек&shy;три&shy;са.</p>
          </div>
          <div id="sol348610"><p>Решение. Ответ: 12.</p></div>
        </body></html>
        """

        with patch("core.services_reshuege.fetch_task_page_html", return_value=html), patch(
            "core.services_reshuege.download_and_replace_images", side_effect=lambda h, *_args, **_kwargs: h
        ):
            import_one_task_from_sdamgia(
                exam_format_id=exam_format.id,
                type_number=7,
                task_id="348610",
                base_url="https://math-oge.sdamgia.ru",
                skip_no_answer=False,
                skip_prototype=False,
                skip_no_solution=False,
                skip_existing=True,
                exclude_larin=False,
                theme="classic",
            )

        task = Task.objects.get(fipi_id="348610")
        v = task.variants.get(theme="classic")
        self.assertNotIn("градус", v.content.lower())
        self.assertIn(r"^{\circ}", v.content)

