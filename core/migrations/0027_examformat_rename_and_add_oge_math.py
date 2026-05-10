from django.db import migrations


def forwards(apps, schema_editor):
    Subject = apps.get_model('core', 'Subject')
    ExamFormat = apps.get_model('core', 'ExamFormat')

    math_profile, _ = Subject.objects.get_or_create(name='Математика (Профиль)')

    fmt = ExamFormat.objects.filter(
        subject=math_profile,
        name='ЕГЭ Профиль',
        year=2024,
    ).first()
    if fmt:
        fmt.name = 'ЕГЭ математика профиль'
        fmt.save(update_fields=['name'])

    math, _ = Subject.objects.get_or_create(name='Математика')
    ExamFormat.objects.get_or_create(
        subject=math,
        name='ОГЭ математика',
        year=2024,
        defaults={'is_active': False},
    )


def backwards(apps, schema_editor):
    Subject = apps.get_model('core', 'Subject')
    ExamFormat = apps.get_model('core', 'ExamFormat')

    math_profile = Subject.objects.filter(name='Математика (Профиль)').first()
    if math_profile:
        fmt = ExamFormat.objects.filter(
            subject=math_profile,
            name='ЕГЭ математика профиль',
            year=2024,
        ).first()
        if fmt:
            fmt.name = 'ЕГЭ Профиль'
            fmt.save(update_fields=['name'])

    math = Subject.objects.filter(name='Математика').first()
    if math:
        ExamFormat.objects.filter(subject=math, name='ОГЭ математика', year=2024).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0026_assignment_deadlines_and_extensions'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

