from django.db import migrations


def forwards(apps, schema_editor):
    ExamFormat = apps.get_model("core", "ExamFormat")
    TaskType = apps.get_model("core", "TaskType")

    for ef in ExamFormat.objects.select_related("subject").all():
        subject_name = (getattr(getattr(ef, "subject", None), "name", "") or "")
        fmt_name = (getattr(ef, "name", "") or "")

        split_after = None
        if "Матем" in subject_name and "ОГЭ" in fmt_name:
            split_after = 19
        elif "Матем" in subject_name and "ЕГЭ" in fmt_name:
            split_after = 12
        elif "Физ" in subject_name and "ЕГЭ" in fmt_name:
            split_after = 20

        if split_after is None:
            continue

        TaskType.objects.filter(exam_format=ef, number__gt=split_after).update(is_extended_answer=True)
        TaskType.objects.filter(exam_format=ef, number__lte=split_after).update(is_extended_answer=False)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0046_seed_ege_physics_tasktypes_and_backfill_extended"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

