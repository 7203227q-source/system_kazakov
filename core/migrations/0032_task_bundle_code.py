from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0031_add_physics_subject_and_formats"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="bundle_code",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=200,
                null=True,
                verbose_name="Код связки (групповой блок)",
            ),
        ),
    ]

