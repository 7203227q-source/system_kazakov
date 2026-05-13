from django.db import migrations


OGE_MATH_TASKTYPE_NAMES_2025 = {
    1: "Практико-ориентированная задача",
    2: "Практико-ориентированная задача",
    3: "Практико-ориентированная задача",
    4: "Практико-ориентированная задача",
    5: "Практико-ориентированная задача",
    6: "Вычисления и преобразования",
    7: "Вычисления и преобразования",
    8: "Алгебраические преобразования",
    9: "Уравнение/неравенство",
    10: "Вероятность и статистика",
    11: "График функции",
    12: "Формулы и зависимости",
    13: "Уравнение/неравенство",
    14: "Математическая модель (практика)",
    15: "Геометрия (вычисления)",
    16: "Геометрия (вычисления)",
    17: "Геометрия (вычисления)",
    18: "Геометрия (вычисления)",
    19: "Геометрия (доказательство)",
    20: "Алгебра (развёрнутый ответ)",
    21: "Алгебра/графики (развёрнутый ответ)",
    22: "Алгебра (высокий уровень)",
    23: "Геометрия (развёрнутый ответ)",
    24: "Доказательство/логика (развёрнутый ответ)",
    25: "Геометрия (высокий уровень)",
}


def forwards(apps, schema_editor):
    ExamFormat = apps.get_model("core", "ExamFormat")
    TaskType = apps.get_model("core", "TaskType")

    for ef in ExamFormat.objects.filter(name__icontains="ОГЭ").select_related("subject"):
        subject_name = getattr(getattr(ef, "subject", None), "name", "") or ""
        if "Матем" not in subject_name:
            continue
        for number in range(1, 26):
            max_points = 2 if number >= 20 else 1
            name = OGE_MATH_TASKTYPE_NAMES_2025.get(number, f"№{number}")
            TaskType.objects.update_or_create(
                exam_format=ef,
                number=number,
                defaults={"name": name, "max_points": max_points},
            )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0041_update_oge_math_tasktype_names"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

