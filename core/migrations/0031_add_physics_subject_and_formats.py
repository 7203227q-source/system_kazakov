from django.db import migrations


def forwards(apps, schema_editor):
    Subject = apps.get_model('core', 'Subject')
    ExamFormat = apps.get_model('core', 'ExamFormat')

    physics, _ = Subject.objects.get_or_create(name='Физика')

    ExamFormat.objects.get_or_create(
        subject=physics,
        name='ЕГЭ физика',
        year=2026,
        defaults={'is_active': True},
    )
    ExamFormat.objects.get_or_create(
        subject=physics,
        name='ОГЭ физика',
        year=2026,
        defaults={'is_active': False},
    )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0030_ensure_oge_math_examformat'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

