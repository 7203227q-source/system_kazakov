from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, StudentSubjectProfile, Task, TaskType, Topic, User


class StudentPendingAssignmentsApiTests(TestCase):
    def test_api_returns_pending_assignments(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")

        subj = Subject.objects.create(name="Физика")
        StudentSubjectProfile.objects.create(student=student, subject=subj)
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subj, name="T")
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1)
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        a1 = Assignment.objects.create(tutor=tutor, student=student, title="A1", is_draft=False, is_completed=False, exam_format=ef)
        a1.tasks.add(task)
        a2 = Assignment.objects.create(tutor=tutor, student=student, title="A2", is_draft=False, is_completed=False, exam_format=ef)
        a2.tasks.add(task)

        self.client.login(username="s", password="pass")
        r = self.client.get(reverse("api_student_pending_assignments"))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        ids = [x.get("id") for x in data.get("assignments", [])]
        self.assertTrue(a1.id in ids)
        self.assertTrue(a2.id in ids)
        self.assertEqual(ids[0], a2.id)
