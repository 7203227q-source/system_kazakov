from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0052_submission_second_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignment",
            name="is_deleted",
            field=models.BooleanField(default=False, verbose_name="Удалено (скрыто у ученика)"),
        ),
        migrations.AddField(
            model_name="assignment",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Когда удалено"),
        ),
        migrations.AddField(
            model_name="assignment",
            name="deleted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="deleted_assignments",
                to="core.user",
                verbose_name="Кем удалено",
            ),
        ),
    ]

