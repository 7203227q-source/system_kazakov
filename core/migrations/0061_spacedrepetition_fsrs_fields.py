from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0060_srs_suspension_and_removal_requests"),
    ]

    operations = [
        migrations.AddField(
            model_name="spacedrepetition",
            name="srs_algorithm",
            field=models.CharField(
                choices=[("sm2", "SM-2"), ("fsrs", "FSRS")],
                db_index=True,
                default="sm2",
                max_length=10,
                verbose_name="Алгоритм интервального повторения",
            ),
        ),
        migrations.AddField(
            model_name="spacedrepetition",
            name="fsrs_state",
            field=models.JSONField(blank=True, default=dict, verbose_name="FSRS state"),
        ),
    ]
