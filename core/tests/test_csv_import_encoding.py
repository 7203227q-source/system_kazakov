import io

from django.test import TestCase

from core.models import ExamFormat, Subject, Task, TaskType
from core.services_csv import import_tasks_from_csv


class CsvImportEncodingTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        TaskType.objects.create(exam_format=self.exam, number=1, name="Тип 1", max_points=1)

    def test_import_cp1251_decodes_russian(self):
        csv_text = (
            "fipi_id,type_number,subtype_tag,difficulty,correct_answer,theme,content,solution\n"
            "abc,1,,50,1,classic,Привет,Решение\n"
        )
        raw = csv_text.encode("cp1251")
        f = io.BytesIO(raw)
        created, updated = import_tasks_from_csv(f, self.exam.id)
        self.assertEqual(created, 1)
        t = Task.objects.get(fipi_id="abc")
        self.assertIn("Привет", t.variants.get(theme="classic").content)

