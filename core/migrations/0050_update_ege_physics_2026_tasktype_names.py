from django.db import migrations


def forwards(apps, schema_editor):
    ExamFormat = apps.get_model("core", "ExamFormat")
    Subject = apps.get_model("core", "Subject")
    TaskType = apps.get_model("core", "TaskType")

    subj = Subject.objects.filter(name="Физика").first()
    if not subj:
        return

    ef = (
        ExamFormat.objects.filter(subject=subj, name="ЕГЭ физика", year=2026)
        .order_by("-is_active", "-id")
        .first()
    )
    if not ef:
        return

    # Источник маппинга: структура демоверсии ЕГЭ-2026 (см. описание тем по номерам заданий).
    # Если в базе уже выставлены осмысленные названия (не "Задание №N"), мы их не трогаем.
    names = {
        1: "Кинематика (равномерное/равноускоренное движение)",
        2: "Динамика (законы Ньютона, силы, трение, тяготение)",
        3: "Законы сохранения (импульс, энергия, работа)",
        4: "Статика/гидростатика/колебания/волны",
        5: "Механика — расчёт 1",
        6: "Механика — расчёт 2",
        7: "МКТ и газовые законы (идеальный газ, изопроцессы)",
        8: "Термодинамика (1 закон, pV-диаграммы, КПД)",
        9: "МКТ/термодинамика — расчёт 1",
        10: "МКТ/термодинамика — расчёт 2",
        11: "Электростатика и постоянный ток (Кулон, Ом, Джоуль–Ленц)",
        12: "Магнитное поле и индукция (Ампер, Лоренц, Фарадей)",
        13: "Колебания/волны и оптика (контур, линзы)",
        14: "Электродинамика — расчёт 1",
        15: "Электродинамика — расчёт 2",
        16: "Квантовая физика (атом, радиоактивность)",
        17: "Квантовая физика — расчёт",
        18: "Межразделная задача — расчёт",
        19: "Межразделная задача 1",
        20: "Межразделная задача 2",
        21: "Качественная задача",
        22: "Расчётная задача (механика)",
        23: "Расчётная задача (МКТ/термодин./электродин.)",
        24: "Задача высокого уровня (МКТ/термодинамика)",
        25: "Задача высокого уровня (электродинамика)",
        26: "Задача высокого уровня (механика)",
    }

    for number, new_name in names.items():
        tt = TaskType.objects.filter(exam_format=ef, number=number).first()
        if not tt:
            continue
        old = (tt.name or "").strip()
        if not old or old == f"Задание №{number}" or old == f"Тип {number}":
            tt.name = new_name
            tt.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0049_submission_ai_last_verify_at"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

