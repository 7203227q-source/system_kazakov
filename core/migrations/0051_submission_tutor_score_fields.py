from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0050_update_ege_physics_2026_tasktype_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="tutor_primary_score",
            field=models.IntegerField(blank=True, null=True, verbose_name="Итог репетитора (первичный балл)"),
        ),
        migrations.AddField(
            model_name="submission",
            name="tutor_scored_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Когда репетитор выставил итог"),
        ),
    ]

