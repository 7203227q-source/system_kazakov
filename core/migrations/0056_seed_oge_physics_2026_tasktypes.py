from django.db import migrations


OGE_PHYSICS_2026_TASKTYPES = {
    1: ("Явления/величины/единицы измерения", 2, False),
    2: ("Приборы и устройства (принцип действия)", 2, False),
    3: ("Распознавание физических явлений", 1, False),
    4: ("Описание явления по признакам/по опыту", 2, False),
    5: ("Объяснение явлений (законы/величины)", 1, False),
    6: ("Вычисление величины (механика)", 1, False),
    7: ("Вычисление величины (механика)", 1, False),
    8: ("Вычисление величины (тепловые явления)", 1, False),
    9: ("Вычисление величины (электромагнитные явления)", 1, False),
    10: ("Вычисление величины (электромагнитные явления)", 1, False),
    11: ("Вычисление величины (квантовые явления)", 1, False),
    12: ("Изменение величин (механика/теплота)", 2, False),
    13: ("Изменение величин (электричество/квант.)", 2, False),
    14: ("Анализ графиков/таблиц/схем", 2, False),
    15: ("Прямые измерения (методология)", 1, False),
    16: ("Анализ исследования/эксперимента (методология)", 2, False),
    17: ("Экспериментальная задача (оборудование)", 3, True),
    18: ("Работа с текстом физического содержания", 2, True),
    19: ("Качественная задача", 2, True),
    20: ("Расчётная задача (повыш.)", 3, True),
    21: ("Расчётная задача (высок.)", 3, True),
    22: ("Расчётная задача (комбинированная)", 3, True),
}


def forwards(apps, schema_editor):
    Subject = apps.get_model("core", "Subject")
    ExamFormat = apps.get_model("core", "ExamFormat")
    TaskType = apps.get_model("core", "TaskType")

    physics, _ = Subject.objects.get_or_create(name="Физика")

    # В проекте формат уже создаётся миграцией 0031, но на всякий случай делаем get_or_create.
    ef, _ = ExamFormat.objects.get_or_create(
        subject=physics,
        name="ОГЭ физика",
        year=2026,
        defaults={"is_active": True},
    )
    if not ef.is_active:
        ef.is_active = True
        ef.save(update_fields=["is_active"])

    for number, (name, max_points, is_extended) in OGE_PHYSICS_2026_TASKTYPES.items():
        tt, created = TaskType.objects.get_or_create(
            exam_format=ef,
            number=number,
            defaults={
                "name": name,
                "max_points": max_points,
                "is_extended_answer": is_extended,
                "is_geometry": False,
            },
        )
        if not created:
            TaskType.objects.filter(id=tt.id).update(
                name=name,
                max_points=max_points,
                is_extended_answer=is_extended,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0055_task_ai_annotated_at_task_ai_annotation_version_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

