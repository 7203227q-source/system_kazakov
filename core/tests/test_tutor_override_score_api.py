from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, Topic, User


class TutorOverrideScoreApiTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor.students.add(self.student)

        subj = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subj, name="T")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=22, name="22", max_points=2, is_extended_answer=True)
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)

        self.assignment = Assignment.objects.create(
            tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=ef
        )
        self.assignment.tasks.add(self.task)

        self.sub = Submission.objects.create(
            student=self.student,
            task=self.task,
            assignment=self.assignment,
            image_url="submissions/x.png",
            primary_score=1,
        )

    def test_tutor_can_override_score(self):
        self.client.login(username="t", password="pass")
        url = reverse("api_tutor_override_score", args=[self.sub.id])
        r = self.client.post(url, data={"tutor_primary_score": "2"})
        self.assertEqual(r.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.tutor_primary_score, 2)

