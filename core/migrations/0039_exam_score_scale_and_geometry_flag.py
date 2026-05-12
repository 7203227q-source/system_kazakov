from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0038_studentsubjectprofile_exam_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="tasktype",
            name="is_geometry",
            field=models.BooleanField(default=False, verbose_name="Геометрия (для ОГЭ)"),
        ),
        migrations.CreateModel(
            name="ExamScoreScale",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("max_primary_score", models.PositiveIntegerField(default=100, verbose_name="Максимальный первичный балл")),
                ("grade_rules", models.JSONField(blank=True, default=list, verbose_name="Правила перевода в оценку (JSON)")),
                (
                    "exam_format",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="score_scale", to="core.examformat"),
                ),
            ],
        ),
    ]

