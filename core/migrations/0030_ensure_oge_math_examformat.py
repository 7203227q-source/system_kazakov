from django.db import migrations


def forwards(apps, schema_editor):
    Subject = apps.get_model('core', 'Subject')
    ExamFormat = apps.get_model('core', 'ExamFormat')

    subject = Subject.objects.filter(name='Математика').first() or Subject.objects.filter(name='Математика (Профиль)').first()
    if not subject:
        return

    ExamFormat.objects.get_or_create(
        subject=subject,
        name='ОГЭ математика',
        year=2024,
        defaults={'is_active': False},
    )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0029_rename_math_profile_subject_to_math'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

