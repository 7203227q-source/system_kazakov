from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, StudentSubjectProfile, Task, TaskType, TaskVariant, Topic, User


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

