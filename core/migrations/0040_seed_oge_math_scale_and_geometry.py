from django.db import migrations


OGE_MATH_RULES_2025 = [
    {"grade": 2, "min_total": 0, "max_total": 7, "min_geometry": None},
    {"grade": 3, "min_total": 8, "max_total": 14, "min_geometry": 2},
    {"grade": 4, "min_total": 15, "max_total": 21, "min_geometry": 2},
    {"grade": 5, "min_total": 22, "max_total": 31, "min_geometry": 2},
]

OGE_MATH_GEOMETRY_NUMBERS = {15, 16, 17, 18, 19}


def forwards(apps, schema_editor):
    Subject = apps.get_model("core", "Subject")
    ExamFormat = apps.get_model("core", "ExamFormat")
    TaskType = apps.get_model("core", "TaskType")
    ExamScoreScale = apps.get_model("core", "ExamScoreScale")

    subject = Subject.objects.filter(name="Математика").first()
    if not subject:
        return

    qs = ExamFormat.objects.filter(subject=subject).filter(name__icontains="ОГЭ")
    for ef in qs:
        ExamScoreScale.objects.get_or_create(
            exam_format=ef,
            defaults={
                "max_primary_score": 31,
                "grade_rules": OGE_MATH_RULES_2025,
            },
        )
        TaskType.objects.filter(exam_format=ef, number__in=OGE_MATH_GEOMETRY_NUMBERS).update(is_geometry=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0039_exam_score_scale_and_geometry_flag"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

