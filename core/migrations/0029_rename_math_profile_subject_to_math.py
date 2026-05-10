from django.db import migrations


def forwards(apps, schema_editor):
    Subject = apps.get_model('core', 'Subject')
    ExamFormat = apps.get_model('core', 'ExamFormat')
    TaskType = apps.get_model('core', 'TaskType')
    Topic = apps.get_model('core', 'Topic')
    Task = apps.get_model('core', 'Task')
    StudentSubjectProfile = apps.get_model('core', 'StudentSubjectProfile')
    DailySnapshot = apps.get_model('core', 'DailySnapshot')
    SubjectAIConfig = apps.get_model('core', 'SubjectAIConfig')

    src = Subject.objects.filter(name='Математика (Профиль)').first()
    if not src:
        return

    dst = Subject.objects.filter(name='Математика').first()
    if not dst:
        src.name = 'Математика'
        src.save(update_fields=['name'])
        return

    for fmt in ExamFormat.objects.filter(subject=src):
        dup = ExamFormat.objects.filter(subject=dst, name=fmt.name, year=fmt.year).first()
        if dup:
            TaskType.objects.filter(exam_format=fmt).update(exam_format=dup)
            fmt.delete()
            continue
        fmt.subject = dst
        fmt.save(update_fields=['subject'])

    for topic in Topic.objects.filter(subject=src):
        dup_topic = Topic.objects.filter(subject=dst, name=topic.name).first()
        if dup_topic:
            Task.objects.filter(topic=topic).update(topic=dup_topic)
            topic.delete()
            continue
        topic.subject = dst
        topic.save(update_fields=['subject'])

    for prof in StudentSubjectProfile.objects.filter(subject=src):
        dup_prof = StudentSubjectProfile.objects.filter(student=prof.student, subject=dst).first()
        if dup_prof:
            dup_prof.target_score = max(int(dup_prof.target_score or 0), int(prof.target_score or 0))
            dup_prof.xp = int(dup_prof.xp or 0) + int(prof.xp or 0)
            dup_prof.level = (int(dup_prof.xp) // 100) + 1
            dup_prof.current_streak = max(int(dup_prof.current_streak or 0), int(prof.current_streak or 0))
            dup_prof.avg_model_error = float(dup_prof.avg_model_error or 0.0)
            dup_prof.trust_factor = float(dup_prof.trust_factor or 0.0)
            if prof.last_verified_date and (not dup_prof.last_verified_date or prof.last_verified_date > dup_prof.last_verified_date):
                dup_prof.last_verified_date = prof.last_verified_date
            dup_prof.learning_velocity = float(dup_prof.learning_velocity or 1.0)
            dup_prof.save()
            prof.delete()
            continue
        prof.subject = dst
        prof.save(update_fields=['subject'])

    for snap in DailySnapshot.objects.filter(subject=src):
        dup_snap = DailySnapshot.objects.filter(student=snap.student, subject=dst, date=snap.date).first()
        if dup_snap:
            dup_snap.current_mastery = max(float(dup_snap.current_mastery or 0.0), float(snap.current_mastery or 0.0))
            dup_snap.predicted_exam_score = max(float(dup_snap.predicted_exam_score or 0.0), float(snap.predicted_exam_score or 0.0))
            dup_snap.gap_between_solo_and_verified = max(float(dup_snap.gap_between_solo_and_verified or 0.0), float(snap.gap_between_solo_and_verified or 0.0))
            dup_snap.rolling_forecast_error = max(float(dup_snap.rolling_forecast_error or 0.0), float(snap.rolling_forecast_error or 0.0))
            dup_snap.save()
            snap.delete()
            continue
        snap.subject = dst
        snap.save(update_fields=['subject'])

    src_cfg = SubjectAIConfig.objects.filter(subject=src).first()
    if src_cfg:
        dst_cfg = SubjectAIConfig.objects.filter(subject=dst).first()
        if not dst_cfg:
            src_cfg.subject = dst
            src_cfg.save(update_fields=['subject'])
        else:
            if not dst_cfg.photo_analysis_model_id and src_cfg.photo_analysis_model_id:
                dst_cfg.photo_analysis_model_id = src_cfg.photo_analysis_model_id
            if not dst_cfg.solution_check_model_id and src_cfg.solution_check_model_id:
                dst_cfg.solution_check_model_id = src_cfg.solution_check_model_id
            if not dst_cfg.image_generate_model_id and src_cfg.image_generate_model_id:
                dst_cfg.image_generate_model_id = src_cfg.image_generate_model_id
            if not dst_cfg.task_regen_text_model_id and src_cfg.task_regen_text_model_id:
                dst_cfg.task_regen_text_model_id = src_cfg.task_regen_text_model_id
            if not dst_cfg.task_regen_image_model_id and src_cfg.task_regen_image_model_id:
                dst_cfg.task_regen_image_model_id = src_cfg.task_regen_image_model_id
            dst_cfg.save()
            src_cfg.delete()

    src.delete()


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0028_move_oge_to_profile_and_remove_math_subject'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

