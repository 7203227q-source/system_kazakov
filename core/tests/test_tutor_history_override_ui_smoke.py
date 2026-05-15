from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import User, Subject, Topic, Task, TaskVariant, Submission


class TutorHistoryOverrideUiSmokeTests(TestCase):
    def test_override_ui_present_in_tutor_history(self):
        tutor = User.objects.create_user(username="t1", password="pw", role="tutor")
        student = User.objects.create_user(username="s1", password="pw", role="student")
        tutor.students.add(student)

        subject = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, correct_answer="1", exam_points=3)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        sub = Submission.objects.create(student=student, task=task, user_answer="", is_correct=False, primary_score=1, score=1)
        Submission.objects.filter(id=sub.id).update(created_at=timezone.now() - timedelta(days=1))

        self.client.force_login(tutor)
        res = self.client.get(f"/tutor/student/{student.id}/history/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Баллы репетитора")

