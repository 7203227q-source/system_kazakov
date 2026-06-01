from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, StudentSubjectProfile, Subject, Task, TaskType, Topic, User


class StudentAssignmentStudentSeqBackfillTests(TestCase):
    def test_student_dashboard_backfills_student_seq_for_existing_assignments(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subj, name="T")
        tt = TaskType.objects.create(exam_format=ef, number=1, name="№1", max_points=1)
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        StudentSubjectProfile.objects.create(student=student, subject=subj, exam_format=ef)

        a1 = Assignment.objects.create(tutor=tutor, student=student, title="A1", is_draft=False, exam_format=ef)
        a1.tasks.add(task)
        a2 = Assignment.objects.create(tutor=tutor, student=student, title="A2", is_draft=False, exam_format=ef)
        a2.tasks.add(task)

        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_dashboard"))
        self.assertEqual(res.status_code, 200)

        seqs = list(
            Assignment.objects.filter(id__in=[a1.id, a2.id]).order_by("created_at", "id").values_list("student_seq", flat=True)
        )
        self.assertEqual(seqs, [1, 2])
