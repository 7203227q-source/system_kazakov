import datetime

from django.test import TestCase
from django.utils import timezone

from core.analytics import update_student_analytics
from core.models import DailySnapshot, ExamFormat, StudentSubjectProfile, Subject, Task, TaskLog, TaskType, Topic, User


class ExamDateForecastTests(TestCase):
    def test_forecast_grows_towards_exam_date_when_trend_positive(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        fmt = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=True)
        profile = StudentSubjectProfile.objects.create(
            student=student,
            subject=subject,
            target_score=80,
            level=1,
            xp=0,
            exam_format=fmt,
            learning_velocity=1.0,
            trust_factor=1.0,
            exam_date=timezone.now().date() + datetime.timedelta(days=10),
        )

        base_date = timezone.now().date() - datetime.timedelta(days=10)
        DailySnapshot.objects.create(student=student, subject=subject, date=base_date, current_mastery=40.0, predicted_exam_score=40.0)
        DailySnapshot.objects.create(student=student, subject=subject, date=timezone.now().date() - datetime.timedelta(days=1), current_mastery=50.0, predicted_exam_score=50.0)

        topic = Topic.objects.create(subject=subject, name="T")
        tt = TaskType.objects.create(exam_format=fmt, number=1, name="Тип 1", max_points=1)
        task = Task.objects.create(topic=topic, task_type=tt, subtype_tag="x", correct_answer="1", difficulty=10, exam_points=1)
        TaskLog.objects.create(student=student, task=task, score=0.5, time_spent=60, is_anomaly=False)

        snap = update_student_analytics(student, subject)
        self.assertGreater(float(snap.predicted_exam_score), 50.0)

