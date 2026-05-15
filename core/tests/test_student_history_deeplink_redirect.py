from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from core.models import User, Subject, Topic, Task, TaskVariant, Submission


class StudentHistoryDeeplinkRedirectTests(TestCase):
    def test_student_history_submission_id_redirects_to_correct_page(self):
        student = User.objects.create_user(username="s1", password="pw", role="student")
        subject = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, correct_answer="1", exam_points=1)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        subs = []
        now = timezone.now()
        for i in range(41):  # 20 on page1, 20 on page2, 1 on page3
            sub = Submission.objects.create(student=student, task=task, user_answer=str(i), is_correct=False, score=0)
            # делаем разные created_at, чтобы порядок был стабильным (последний — самый старый)
            Submission.objects.filter(id=sub.id).update(created_at=now - timedelta(minutes=i))
            subs.append(sub)

        target = subs[-1]
        self.client.force_login(student)
        res = self.client.get(f"/student/history/?submission_id={target.id}")
        self.assertEqual(res.status_code, 302)
        self.assertIn("page=3", res["Location"])
        self.assertIn(f"submission_id={target.id}", res["Location"])
