from unittest.mock import patch

from django.test import TestCase

from core.models import ExamFormat, Subject, Task, TaskType, Topic
from core.services_reshuege import import_one_task_from_sdamgia


class SdamgiaBundleImportTests(TestCase):
    def test_import_sets_bundle_code_and_imports_others(self):
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)
        TaskType.objects.create(exam_format=exam_format, number=2, name="Тип 2", max_points=1)
        TaskType.objects.create(exam_format=exam_format, number=3, name="Тип 3", max_points=1)
        TaskType.objects.create(exam_format=exam_format, number=4, name="Тип 4", max_points=1)
        TaskType.objects.create(exam_format=exam_format, number=5, name="Тип 5", max_points=1)

        html = """
        <html><body>
        <div id="body408182">Условие. Ответ: 213.</div>
        <div id="sol408182">Решение. Ответ: 213.</div>
        <div class="expand" data-open="Показать другие задания этого блока" data-close="Скрыть">
          <div class="prob_maindiv">Тип 2 № 408186</div>
          <div class="prob_maindiv">Тип 3 № 408188</div>
          <div class="prob_maindiv">Тип 4 № 408190</div>
          <div class="prob_maindiv">Тип 5 № 408193</div>
        </div>
        </body></html>
        """

        def fetch(_base_url, task_id):
            return html.replace("408182", str(task_id))

        with patch("core.services_reshuege.fetch_task_page_html", side_effect=fetch), patch(
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

        tasks = list(Task.objects.filter(fipi_id__in=["408182", "408186", "408188", "408190", "408193"]))
        self.assertEqual(len(tasks), 5)
        codes = {t.bundle_code for t in tasks}
        self.assertEqual(len(codes), 1)
        self.assertTrue(next(iter(codes)))

