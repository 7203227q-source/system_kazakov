from django.test import TestCase

from core.models import User, Subject, Topic, Task, TaskVariant, Submission


class StudentHistoryPaginationTests(TestCase):
    def test_student_history_paginated_20_per_page(self):
        student = User.objects.create_user(username="s1", password="pw", role="student")
        subject = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, correct_answer="1", exam_points=1)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        for i in range(25):
            Submission.objects.create(student=student, task=task, user_answer=str(i), is_correct=False, score=0)

        self.client.force_login(student)

        res1 = self.client.get("/student/history/")
        self.assertEqual(res1.status_code, 200)
        self.assertIn("page_obj", res1.context)
        self.assertEqual(len(res1.context["submissions"]), 20)

        res2 = self.client.get("/student/history/?page=2")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(len(res2.context["submissions"]), 5)
