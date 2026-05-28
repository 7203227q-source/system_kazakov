import django.db.models
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0059_submission_ai_photo_valid_and_breakdown"),
    ]

    operations = [
        migrations.AddField(
            model_name="spacedrepetition",
            name="is_suspended",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.CreateModel(
            name="SpacedRepetitionRemovalRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("comment", models.TextField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Ожидает"), ("approved", "Одобрено"), ("rejected", "Отклонено")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "student",
                    models.ForeignKey(
                        limit_choices_to={"role": "student"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="srs_removal_requests_as_student",
                        to="core.user",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.task"),
                ),
                (
                    "tutor",
                    models.ForeignKey(
                        limit_choices_to={"role": "tutor"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="srs_removal_requests_as_tutor",
                        to="core.user",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="spacedrepetitionremovalrequest",
            index=models.Index(fields=["tutor", "status", "created_at"], name="core_spaced_tutor_srs_idx"),
        ),
        migrations.AddIndex(
            model_name="spacedrepetitionremovalrequest",
            index=models.Index(fields=["student", "status", "created_at"], name="core_spaced_student_srs_idx"),
        ),
        migrations.AddConstraint(
            model_name="spacedrepetitionremovalrequest",
            constraint=models.UniqueConstraint(
                condition=django.db.models.Q(status="pending"),
                fields=("student", "task"),
                name="uniq_pending_srs_removal_request",
            ),
        ),
    ]
