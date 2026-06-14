import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0066_student_learning_plan"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignment",
            name="assignment_mode",
            field=models.CharField(
                choices=[("exam", "Экзамен"), ("school", "Школьная программа")],
                default="exam",
                max_length=20,
                verbose_name="Режим варианта",
            ),
        ),
        migrations.AddField(
            model_name="assignment",
            name="curriculum_topic",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assignments",
                to="core.curriculumtopic",
            ),
        ),
        migrations.AddField(
            model_name="assignment",
            name="learning_task_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assignments",
                to="core.learningtasktype",
            ),
        ),
        migrations.AddField(
            model_name="assignment",
            name="learning_track",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assignments",
                to="core.learningtrack",
            ),
        ),
    ]
