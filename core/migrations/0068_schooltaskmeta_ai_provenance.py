from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0067_assignment_school_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="schooltaskmeta",
            name="generated_by_ai",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="schooltaskmeta",
            name="generated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="generated_school_tasks",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="schooltaskmeta",
            name="generation_notes",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
