from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0051_submission_tutor_score_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="image_url_2",
            field=models.ImageField(blank=True, null=True, upload_to="submissions/", verbose_name="Фото решения/черновика (стр. 2)"),
        ),
    ]

