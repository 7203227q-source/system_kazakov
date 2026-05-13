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

    qs = ExamFormat.objects.filter(subject__name="Математика", name__icontains="ОГЭ")
    for ef in qs:
        for number, name in OGE_MATH_TASKTYPE_NAMES_2025.items():
            TaskType.objects.filter(exam_format=ef, number=number).update(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0040_seed_oge_math_scale_and_geometry"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

