from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, Submission, SubmissionComment, User


class SubmissionCommentUnreadTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create(username="t", role="tutor")
        self.student = User.objects.create(username="s", role="student")
        self.student.tutors.add(self.tutor)

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

    def test_student_message_is_unseen_for_tutor(self):
        self.client.force_login(self.student)
        url = reverse("student_add_submission_comment", args=[self.assignment.id, self.task.id])
        res = self.client.post(url, {"text": "q"})
        self.assertEqual(res.status_code, 200)

        c = SubmissionComment.objects.get(submission=self.sub)
        self.assertIsNotNone(c.seen_by_student_at)
        self.assertIsNone(c.seen_by_tutor_at)

    def test_tutor_message_is_unseen_for_student(self):
        self.client.force_login(self.tutor)
        url = reverse("tutor_add_submission_comment", args=[self.sub.id])
        res = self.client.post(url, {"text": "a"})
        self.assertEqual(res.status_code, 200)

        c = SubmissionComment.objects.get(submission=self.sub)
        self.assertIsNotNone(c.seen_by_tutor_at)
        self.assertIsNone(c.seen_by_student_at)

    def test_student_history_marks_tutor_replies_seen(self):
        SubmissionComment.objects.create(submission=self.sub, author=self.tutor, author_role="tutor", text="a", seen_by_tutor_at=None, seen_by_student_at=None)

        self.client.force_login(self.student)
        res = self.client.get(reverse("student_history"))
        self.assertEqual(res.status_code, 200)

        c = SubmissionComment.objects.get(submission=self.sub)
        self.assertIsNotNone(c.seen_by_student_at)

    def test_tutor_history_marks_student_questions_seen(self):
        self.client.force_login(self.student)
        self.client.post(reverse("student_add_submission_comment", args=[self.assignment.id, self.task.id]), {"text": "q"})
        c = SubmissionComment.objects.get(submission=self.sub)
        self.assertIsNone(c.seen_by_tutor_at)

        self.client.force_login(self.tutor)
        res = self.client.get(reverse("tutor_student_history", args=[self.student.id]))
        self.assertEqual(res.status_code, 200)

        c.refresh_from_db()
        self.assertIsNotNone(c.seen_by_tutor_at)

