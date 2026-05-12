from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, Subject, StudentSubjectProfile, Submission, Task, TaskType, TaskVariant, Topic, User


class TutorSolveRateDecayTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        self.subject = Subject.objects.create(name="Математика")
        self.ef_a = ExamFormat.objects.create(subject=self.subject, name="ОГЭ", year=2025, is_active=True)
        self.ef_b = ExamFormat.objects.create(subject=self.subject, name="ОГЭ", year=2026, is_active=False)

        TaskType.objects.create(exam_format=self.ef_a, number=1, name="N1", max_points=1)
        self.tt2 = TaskType.objects.create(exam_format=self.ef_b, number=2, name="N2", max_points=1)

        topic = Topic.objects.create(subject=self.subject, name="T")
        t = Task.objects.create(topic=topic, task_type=self.tt2, correct_answer="2", difficulty=50, exam_points=1)
        TaskVariant.objects.create(task=t, theme="classic", content="<p>U</p>", solution="<p>S</p>")

        StudentSubjectProfile.objects.create(student=self.student, subject=self.subject, exam_format=self.ef_b)

    def test_task_type_tiles_follow_student_exam_format(self):
        self.client.login(username="t", password="pass")
        res = self.client.get(
            reverse("tutor_dashboard"),
            {"student_id": self.student.id, "subject_id": self.subject.id},
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, ">2<")
        self.assertNotContains(res, ">1<")

    def test_solve_rate_uses_last_attempt_per_task(self):
        task = Task.objects.filter(task_type=self.tt2).first()
        now = timezone.now()
        old = now - timezone.timedelta(days=14)

        s_old = Submission.objects.create(student=self.student, task=task, user_answer="2", is_correct=True, score=1)
        Submission.objects.filter(id=s_old.id).update(created_at=old)
        s_new = Submission.objects.create(student=self.student, task=task, user_answer="1", is_correct=False, score=0)
        Submission.objects.filter(id=s_new.id).update(created_at=now)

        self.client.login(username="t", password="pass")
        res = self.client.get(
            reverse("tutor_dashboard"),
            {"student_id": self.student.id, "subject_id": self.subject.id},
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, ">2<")
        self.assertContains(res, 'data-rate="0"')

    def test_solve_rate_decays_old_attempts(self):
        topic = Topic.objects.filter(subject=self.subject).first()
        t2 = Task.objects.create(topic=topic, task_type=self.tt2, correct_answer="5", difficulty=50, exam_points=1)
        TaskVariant.objects.create(task=t2, theme="classic", content="<p>U</p>", solution="<p>S</p>")

        tasks = list(Task.objects.filter(task_type=self.tt2).order_by("id")[:2])
        t_old, t_new = tasks[0], tasks[1]
        now = timezone.now()
        old = now - timezone.timedelta(days=14)

        s1 = Submission.objects.create(student=self.student, task=t_old, user_answer=t_old.correct_answer, is_correct=True, score=1)
        Submission.objects.filter(id=s1.id).update(created_at=old)
        s2 = Submission.objects.create(student=self.student, task=t_new, user_answer="0", is_correct=False, score=0)
        Submission.objects.filter(id=s2.id).update(created_at=now)

        self.client.login(username="t", password="pass")
        res = self.client.get(
            reverse("tutor_dashboard"),
            {"student_id": self.student.id, "subject_id": self.subject.id},
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, ">2<")
        self.assertContains(res, 'data-rate="33"')
