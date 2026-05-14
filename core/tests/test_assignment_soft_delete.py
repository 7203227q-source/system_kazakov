from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, StudentSubjectProfile, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class AssignmentSoftDeleteTests(TestCase):
    def test_soft_delete_hides_assignment_but_keeps_submissions(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        StudentSubjectProfile.objects.create(student=student, subject=subj, exam_format=ef, xp=0, level=1, target_score=80)

        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1, subtype_tag="A")
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        a = Assignment.objects.create(tutor=tutor, student=student, title="Вариант X", is_draft=False, exam_format=ef)
        a.tasks.add(task)
        sub = Submission.objects.create(student=student, task=task, assignment=a, user_answer="1", is_correct=True, score=1)

        self.client.login(username="t", password="pass")
        res = self.client.post(reverse("tutor_delete_assignment", args=[a.id]))
        self.assertEqual(res.status_code, 302)

        a.refresh_from_db()
        self.assertTrue(a.is_deleted)
        self.assertTrue(Submission.objects.filter(id=sub.id).exists())

        self.client.login(username="s", password="pass")
        dash = self.client.get(reverse("student_dashboard"))
        self.assertEqual(dash.status_code, 200)
        self.assertNotIn("Вариант X", dash.content.decode("utf-8"))

