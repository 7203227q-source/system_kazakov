from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, StudentSubjectProfile, Subject, Task, TaskType, TaskVariant, Topic, User


class SrsSubjectPersistsOnPostTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        self.math = Subject.objects.create(name="Математика")
        self.phys = Subject.objects.create(name="Физика")
        self.math_fmt = ExamFormat.objects.create(subject=self.math, name="ЕГЭ матем", year=2026, is_active=True)
        self.phys_fmt = ExamFormat.objects.create(subject=self.phys, name="ЕГЭ физ", year=2026, is_active=True)

        StudentSubjectProfile.objects.create(student=self.student, subject=self.phys, exam_format=self.phys_fmt)
        StudentSubjectProfile.objects.create(student=self.student, subject=self.math, exam_format=self.math_fmt)

        today = timezone.localdate()

        tt_m = TaskType.objects.create(exam_format=self.math_fmt, number=1, name="M", max_points=1, is_extended_answer=False)
        topic_m = Topic.objects.create(subject=self.math, name="Tm")
        self.task_m = Task.objects.create(topic=topic_m, task_type=tt_m, correct_answer="1", difficulty=10, exam_points=1)
        TaskVariant.objects.create(task=self.task_m, theme="classic", content="<p>MATH_TASK</p>", solution="<p>S</p>")
        SpacedRepetition.objects.create(student=self.student, task=self.task_m, next_review_date=today)

        tt_p = TaskType.objects.create(exam_format=self.phys_fmt, number=1, name="P", max_points=1, is_extended_answer=False)
        topic_p = Topic.objects.create(subject=self.phys, name="Tp")
        self.task_p = Task.objects.create(topic=topic_p, task_type=tt_p, correct_answer="1", difficulty=10, exam_points=1)
        TaskVariant.objects.create(task=self.task_p, theme="classic", content="<p>PHYS_TASK</p>", solution="<p>S</p>")
        SpacedRepetition.objects.create(student=self.student, task=self.task_p, next_review_date=today)

    def test_srs_answer_form_includes_subject_id_hidden_input(self):
        self.client.force_login(self.student)
        url = reverse("student_practice") + f"?mode=srs&subject_id={self.math.id}"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")
        self.assertIn('name="subject_id"', html)
        self.assertIn(f'value="{self.math.id}"', html)

    def test_srs_post_without_subject_id_keeps_current_subject(self):
        self.client.force_login(self.student)
        url = reverse("student_practice") + f"?mode=srs&subject_id={self.math.id}"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        token = res.context.get("attempt_token")
        self.assertTrue(token)

        res2 = self.client.post(
            reverse("student_practice"),
            {
                "task_id": str(self.task_m.id),
                "mode": "srs",
                "attempt_token": token,
                "answer": "1",
            },
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(int(res2.context.get("subject_id") or 0), int(self.math.id))
        self.assertEqual(int(res2.context.get("srs_due_remaining") or 0), 0)

