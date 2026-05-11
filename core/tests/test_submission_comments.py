from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, Submission, User


class SubmissionCommentModelTests(TestCase):
    def test_comment_attaches_to_submission(self):
        tutor = User.objects.create(username="t", role="tutor")
        student = User.objects.create(username="s", role="student")
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)
        task = Task.objects.create(
            topic=topic,
            task_type=task_type,
            fipi_id="1",
            correct_answer="1",
            difficulty=10,
            exam_points=1,
        )

        assignment = Assignment.objects.create(tutor=tutor, student=student, title="Вариант 1")
        assignment.tasks.add(task)

        sub = Submission.objects.create(student=student, task=task, assignment=assignment, user_answer="", is_correct=None)
        c = sub.comments.create(author=student, author_role="student", text="Вопрос?")

        self.assertEqual(c.submission_id, sub.id)
        self.assertEqual(sub.comments.count(), 1)


class SubmissionCommentEndpointTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create(username="t", role="tutor")
        self.student = User.objects.create(username="s", role="student")
        self.other_student = User.objects.create(username="s2", role="student")

        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)
        self.task = Task.objects.create(
            topic=topic,
            task_type=task_type,
            fipi_id="1",
            correct_answer="1",
            difficulty=10,
            exam_points=1,
        )

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="Вариант 1")
        self.assignment.tasks.add(self.task)
        self.sub = Submission.objects.create(student=self.student, task=self.task, assignment=self.assignment, user_answer="", is_correct=None)

    def test_student_can_post_comment_for_own_assignment_task(self):
        self.client.force_login(self.student)
        url = reverse("student_add_submission_comment", args=[self.assignment.id, self.task.id])
        res = self.client.post(url, {"text": "Вопрос"})
        self.assertEqual(res.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.comments.count(), 1)

    def test_student_cannot_post_comment_for_other_student_assignment(self):
        self.client.force_login(self.other_student)
        url = reverse("student_add_submission_comment", args=[self.assignment.id, self.task.id])
        res = self.client.post(url, {"text": "Вопрос"})
        self.assertEqual(res.status_code, 403)

    def test_tutor_can_post_comment_for_own_student_submission(self):
        self.client.force_login(self.tutor)
        url = reverse("tutor_add_submission_comment", args=[self.sub.id])
        res = self.client.post(url, {"text": "Ответ"})
        self.assertEqual(res.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.comments.count(), 1)

    def test_tutor_cannot_post_comment_for_foreign_submission(self):
        tutor2 = User.objects.create(username="t2", role="tutor")
        self.client.force_login(tutor2)
        url = reverse("tutor_add_submission_comment", args=[self.sub.id])
        res = self.client.post(url, {"text": "Ответ"})
        self.assertEqual(res.status_code, 403)


class SubmissionCheckCommentsResponseTests(TestCase):
    def test_check_returns_comment_flags(self):
        tutor = User.objects.create(username="t", role="tutor")
        student = User.objects.create(username="s", role="student")
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)
        task = Task.objects.create(
            topic=topic,
            task_type=task_type,
            fipi_id="1",
            correct_answer="2",
            difficulty=10,
            exam_points=1,
        )
        assignment = Assignment.objects.create(tutor=tutor, student=student, title="Вариант 1")
        assignment.tasks.add(task)

        self.client.force_login(student)
        url = reverse("student_check_assignment_task", args=[assignment.id, task.id])
        res = self.client.post(url, {"answer": "2"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("comments_count", data)
        self.assertIn("can_view_comments", data)
        self.assertIn("submission_id", data)

