from unittest.mock import patch

from django.test import TestCase

from core.models import ExamFormat, Subject, Task, TaskType, Topic
from core.services_reshuege import import_one_task_from_sdamgia


class SdamgiaExpandTextBlockImportTests(TestCase):
    def test_import_prefers_text_task_id_block_over_body(self):
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)

        html = """
        <html><body>
          <div id="body999999"><p>Короткий текст без картинки</p></div>
          <div id="text408182">
            <p>Полный текст</p>
            <img src="/get_file?id=1">
          </div>
          <div id="sol408182"><p>Решение. Ответ: 213.</p></div>
          Ответ: 213.
        </body></html>
        """

        with patch("core.services_reshuege.fetch_task_page_html", return_value=html), patch(
            "core.services_reshuege.download_and_replace_images", side_effect=lambda h, *_args, **_kwargs: h
        ):
            import_one_task_from_sdamgia(
                exam_format_id=exam_format.id,
                type_number=1,
                task_id="408182",
                base_url="https://math-oge.sdamgia.ru",
                skip_no_answer=False,
                skip_prototype=False,
                skip_no_solution=False,
                skip_existing=True,
                exclude_larin=False,
                theme="classic",
            )

        task = Task.objects.get(fipi_id="408182")
        v = task.variants.get(theme="classic")
        self.assertIn('id="text408182"', v.content)
        self.assertIn("/get_file?id=1", v.content)
        self.assertNotIn("Короткий текст", v.content)

