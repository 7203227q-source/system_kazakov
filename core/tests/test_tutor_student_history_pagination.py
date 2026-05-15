from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import User, Subject, Topic, Task, TaskVariant, Submission


class TutorStudentHistoryPaginationTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t1", password="pw", role="tutor")
        self.student = User.objects.create_user(username="s1", password="pw", role="student")
        self.tutor.students.add(self.student)

        subject = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, correct_answer="1", exam_points=1)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

    def test_pagination_by_days_14(self):
        now = timezone.now()
        for i in range(20):
            sub = Submission.objects.create(student=self.student, task=self.task, user_answer="1", is_correct=True, score=1)
            Submission.objects.filter(id=sub.id).update(created_at=now - timedelta(days=i))

        self.client.force_login(self.tutor)
        res1 = self.client.get(f"/tutor/student/{self.student.id}/history/")
        self.assertEqual(res1.status_code, 200)
        self.assertIn("page_obj", res1.context)
        self.assertEqual(len(res1.context["history_days"]), 14)

        res2 = self.client.get(f"/tutor/student/{self.student.id}/history/?page=2")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(len(res2.context["history_days"]), 6)

    def test_deeplink_redirects_to_correct_page(self):
        now = timezone.now()
        target_sub = None
        for i in range(20):
            sub = Submission.objects.create(student=self.student, task=self.task, user_answer="1", is_correct=True, score=1)
            Submission.objects.filter(id=sub.id).update(created_at=now - timedelta(days=i))
            if i == 19:
                target_sub = sub

        self.client.force_login(self.tutor)
        res = self.client.get(f"/tutor/student/{self.student.id}/history/?submission_id={target_sub.id}")
        self.assertEqual(res.status_code, 302)
        self.assertIn("page=2", res["Location"])
        self.assertIn(f"submission_id={target_sub.id}", res["Location"])

