from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0063_add_english_subject_and_admins"),
    ]

    operations = [
        migrations.CreateModel(
            name="LearningTrack",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(choices=[("school", "Школьная программа")], max_length=20)),
                ("grade", models.PositiveSmallIntegerField()),
                ("title", models.CharField(max_length=200)),
                ("academic_year", models.CharField(blank=True, max_length=32, null=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "subject",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="learning_tracks",
                        to="core.subject",
                    ),
                ),
            ],
            options={
                "ordering": ["grade", "title", "id"],
            },
        ),
        migrations.CreateModel(
            name="CurriculumUnit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("position", models.PositiveIntegerField()),
                ("description", models.TextField(blank=True, null=True)),
                (
                    "learning_track",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="units",
                        to="core.learningtrack",
                    ),
                ),
            ],
            options={
                "ordering": ["position", "id"],
            },
        ),
        migrations.CreateModel(
            name="LearningTaskType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=64)),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("default_max_points", models.PositiveSmallIntegerField(default=1)),
                ("is_extended_answer", models.BooleanField(default=False)),
                (
                    "learning_track",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="learning_task_types",
                        to="core.learningtrack",
                    ),
                ),
            ],
            options={
                "ordering": ["name", "id"],
            },
        ),
        migrations.CreateModel(
            name="CurriculumTopic",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("position", models.PositiveIntegerField()),
                ("difficulty_baseline", models.PositiveSmallIntegerField(default=1)),
                ("is_required", models.BooleanField(default=True)),
                (
                    "legacy_topic",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="curriculum_topics",
                        to="core.topic",
                    ),
                ),
                (
                    "unit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="topics",
                        to="core.curriculumunit",
                    ),
                ),
            ],
            options={
                "ordering": ["position", "id"],
            },
        ),
        migrations.CreateModel(
            name="SchoolTaskMeta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("difficulty_level", models.PositiveSmallIntegerField(default=1)),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Черновик"), ("published", "Опубликовано")],
                        default="draft",
                        max_length=20,
                    ),
                ),
                (
                    "curriculum_topic",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="school_task_meta",
                        to="core.curriculumtopic",
                    ),
                ),
                (
                    "learning_task_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="school_task_meta",
                        to="core.learningtasktype",
                    ),
                ),
                (
                    "learning_track",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="school_task_meta",
                        to="core.learningtrack",
                    ),
                ),
                (
                    "task",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="school_meta",
                        to="core.task",
                    ),
                ),
            ],
            options={
                "ordering": ["learning_track", "curriculum_topic", "learning_task_type", "task_id"],
            },
        ),
        migrations.AddConstraint(
            model_name="learningtrack",
            constraint=models.UniqueConstraint(
                fields=("subject", "mode", "grade", "title"),
                name="uniq_learning_track_subject_mode_grade_title",
            ),
        ),
        migrations.AddConstraint(
            model_name="curriculumunit",
            constraint=models.UniqueConstraint(
                fields=("learning_track", "position"),
                name="uniq_curriculum_unit_learning_track_position",
            ),
        ),
        migrations.AddConstraint(
            model_name="learningtasktype",
            constraint=models.UniqueConstraint(
                fields=("learning_track", "code"),
                name="uniq_learning_task_type_learning_track_code",
            ),
        ),
        migrations.AddConstraint(
            model_name="curriculumtopic",
            constraint=models.UniqueConstraint(
                fields=("unit", "position"),
                name="uniq_curriculum_topic_unit_position",
            ),
        ),
    ]
