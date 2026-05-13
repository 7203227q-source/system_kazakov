from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0048_submission_show_solution_allowed"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="ai_last_verify_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Последняя попытка ИИ-проверки"),
        ),
    ]

