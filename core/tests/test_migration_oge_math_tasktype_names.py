from django.db import connection
from django.test import TransactionTestCase

from django.db.migrations.executor import MigrationExecutor


class OgeMathTaskTypeNamesMigrationTests(TransactionTestCase):
    app = "core"

    migrate_from = ("core", "0022_openroutermodel_subjectaiconfig")
    migrate_to = ("core", "0023_update_oge_math_tasktype_names")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        apps = executor.loader.project_state([self.migrate_from]).apps

        Subject = apps.get_model("core", "Subject")
        ExamFormat = apps.get_model("core", "ExamFormat")
        TaskType = apps.get_model("core", "TaskType")

        self.subject = Subject.objects.create(name="Математика")
        self.ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ математика", year=2025, is_active=True)
        self.ef_id = self.ef.id
        for n in range(1, 26):
            TaskType.objects.create(exam_format=self.ef, number=n, name=f"N{n}", max_points=2 if n >= 20 else 1)

    def test_names_are_updated(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        apps = executor.loader.project_state([self.migrate_to]).apps
        TaskType = apps.get_model("core", "TaskType")

        with connection.cursor() as cur:
            cur.execute(
                "select count(1) from django_migrations where app=%s and name=%s",
                ["core", "0023_update_oge_math_tasktype_names"],
            )
            self.assertEqual(cur.fetchone()[0], 1)

        t1 = TaskType.objects.get(exam_format_id=self.ef_id, number=1)
        t15 = TaskType.objects.get(exam_format_id=self.ef_id, number=15)
        t20 = TaskType.objects.get(exam_format_id=self.ef_id, number=20)

        self.assertNotEqual(t1.name, "N1")
        self.assertNotEqual(t15.name, "N15")
        self.assertNotEqual(t20.name, "N20")
