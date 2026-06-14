from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0065_seed_math_grade7_track"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudentLearningPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "goal_type",
                    models.CharField(
                        choices=[
                            ("подтянуть базу", "Подтянуть базу"),
                            ("идти по школьной программе", "Идти по школьной программе"),
                            ("ускоренный проход", "Ускоренный проход"),
                        ],
                        max_length=64,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Черновик"), ("active", "Активный"), ("completed", "Завершён")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("diagnostic_completed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_learning_plans",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "learning_track",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="learning_plans",
                        to="core.learningtrack",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        limit_choices_to={"role": "student"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="learning_plans",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="PlanItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("priority", models.PositiveSmallIntegerField(default=1)),
                ("target_mastery", models.DecimalField(decimal_places=2, default=Decimal("0.80"), max_digits=4)),
                ("recommended_task_count", models.PositiveSmallIntegerField(default=5)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("assigned", "Назначено"),
                            ("in_progress", "В работе"),
                            ("repeat", "Повторить"),
                            ("mastered", "Освоено"),
                        ],
                        default="assigned",
                        max_length=20,
                    ),
                ),
                ("next_review_at", models.DateTimeField(blank=True, null=True)),
                (
                    "curriculum_topic",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="plan_items",
                        to="core.curriculumtopic",
                    ),
                ),
                (
                    "plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="core.studentlearningplan",
                    ),
                ),
            ],
            options={
                "ordering": ["-priority", "id"],
            },
        ),
    ]
