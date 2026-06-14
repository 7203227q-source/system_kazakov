from django.db import migrations


UNIT_TITLES = [
    "Рациональные числа",
    "Алгебраические выражения",
    "Линейные уравнения",
    "Геометрические фигуры",
]


def forwards(apps, schema_editor):
    Subject = apps.get_model("core", "Subject")
    LearningTrack = apps.get_model("core", "LearningTrack")
    CurriculumUnit = apps.get_model("core", "CurriculumUnit")

    math_subject, _ = Subject.objects.get_or_create(name="Математика")
    learning_track, _ = LearningTrack.objects.get_or_create(
        subject=math_subject,
        mode="school",
        grade=7,
        title="Математика, 7 класс",
        defaults={"is_active": True},
    )

    for position, title in enumerate(UNIT_TITLES, start=1):
        CurriculumUnit.objects.get_or_create(
            learning_track=learning_track,
            position=position,
            defaults={"title": title},
        )


def backwards(apps, schema_editor):
    LearningTrack = apps.get_model("core", "LearningTrack")

    LearningTrack.objects.filter(
        mode="school",
        grade=7,
        title="Математика, 7 класс",
        subject__name="Математика",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0064_school_track_models"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
