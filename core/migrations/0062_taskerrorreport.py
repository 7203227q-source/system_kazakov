import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0061_spacedrepetition_fsrs_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="TaskErrorReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "reporter_role",
                    models.CharField(
                        choices=[("student", "Ученик"), ("tutor", "Репетитор")],
                        max_length=20,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("practice", "Тренажер"),
                            ("srs", "Интервальные повторения"),
                            ("variant", "Вариант"),
                            ("student_history", "Журнал ученика"),
                            ("tutor_history", "Журнал репетитора"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("new", "Новая"), ("reviewed", "Просмотрена"), ("resolved", "Решена")],
                        default="new",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assignment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="task_error_reports",
                        to="core.assignment",
                    ),
                ),
                (
                    "reported_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="task_error_reports",
                        to="core.user",
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="task_error_reports",
                        to="core.submission",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="error_reports",
                        to="core.task",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="taskerrorreport",
            constraint=models.UniqueConstraint(
                fields=("task", "reported_by", "reporter_role", "source", "submission", "assignment"),
                name="uniq_task_error_report_context",
            ),
        ),
    ]
