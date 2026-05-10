from django.db import migrations


def forwards(apps, schema_editor):
    Subject = apps.get_model('core', 'Subject')
    ExamFormat = apps.get_model('core', 'ExamFormat')
    Topic = apps.get_model('core', 'Topic')

    math_profile = Subject.objects.filter(name='Математика (Профиль)').first()
    if not math_profile:
        return

    math = Subject.objects.filter(name='Математика').first()
    if math:
        oge = ExamFormat.objects.filter(subject=math, name='ОГЭ математика', year=2024).first()
        if oge:
            oge.subject = math_profile
            oge.save(update_fields=['subject'])

        has_topics = Topic.objects.filter(subject=math).exists()
        has_formats = ExamFormat.objects.filter(subject=math).exists()
        if not has_topics and not has_formats:
            math.delete()


def backwards(apps, schema_editor):
    Subject = apps.get_model('core', 'Subject')
    ExamFormat = apps.get_model('core', 'ExamFormat')

    math_profile = Subject.objects.filter(name='Математика (Профиль)').first()
    if not math_profile:
        return

    math, _ = Subject.objects.get_or_create(name='Математика')
    oge = ExamFormat.objects.filter(subject=math_profile, name='ОГЭ математика', year=2024).first()
    if oge:
        oge.subject = math
        oge.save(update_fields=['subject'])


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0027_examformat_rename_and_add_oge_math'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

