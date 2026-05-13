from django.db import migrations


def forwards(apps, schema_editor):
    ExamFormat = apps.get_model("core", "ExamFormat")
    TaskType = apps.get_model("core", "TaskType")

    def _ensure_tasktype(exam_format, number, *, max_points, is_extended):
        TaskType.objects.update_or_create(
            exam_format=exam_format,
            number=number,
            defaults={
                "name": f"Задание №{number}",
                "max_points": int(max_points),
                "is_extended_answer": bool(is_extended),
            },
        )

    # --- ЕГЭ физика ---
    ef = (
        ExamFormat.objects.filter(name="ЕГЭ физика", year=2026)
        .select_related("subject")
        .order_by("-is_active", "-year", "id")
        .first()
    )
    if ef:
        part1_two_points = {5, 6, 9, 10, 14, 15, 17, 18}
        part2_points = {21: 3, 22: 2, 23: 2, 24: 3, 25: 3, 26: 4}

        for n in range(1, 27):
            if n <= 20:
                mp = 2 if n in part1_two_points else 1
                _ensure_tasktype(ef, n, max_points=mp, is_extended=False)
            else:
                mp = part2_points.get(n, 3)
                _ensure_tasktype(ef, n, max_points=mp, is_extended=True)

    # --- Backfill: математика ---
    for fmt in ExamFormat.objects.filter(name__icontains="Матем"):
        split_after = None
        if "ОГЭ" in (fmt.name or ""):
            split_after = 19
        elif "ЕГЭ" in (fmt.name or ""):
            split_after = 12
        if split_after is None:
            continue
        TaskType.objects.filter(exam_format=fmt, number__gt=split_after).update(is_extended_answer=True)
        TaskType.objects.filter(exam_format=fmt, number__lte=split_after).update(is_extended_answer=False)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0045_tasktype_is_extended_answer"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

