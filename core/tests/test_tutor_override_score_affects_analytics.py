from django.test import TestCase

from core.analytics import record_task_log
from core.models import ExamFormat, Subject, Submission, Task, TaskType, Topic, User


class TutorOverrideScoreAffectsAnalyticsTests(TestCase):
    def test_record_task_log_uses_tutor_primary_score_when_present(self):
        subj = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subj, name="T")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=26, name="26", max_points=4)
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=4)

        student = User.objects.create_user(username="s", password="pass", role="student")
        sub = Submission.objects.create(student=student, task=task, is_correct=False, primary_score=1)

        # Репетитор исправил оценку: 3/4
        sub.tutor_primary_score = 3
        sub.save(update_fields=["tutor_primary_score"])

        log = record_task_log(student, task, sub, assignment=None, time_spent=30)
        self.assertEqual(float(log.score), 3.0)

