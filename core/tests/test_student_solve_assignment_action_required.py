from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User


class StudentSolveAssignmentActionRequiredTests(TestCase):
    def test_post_without_action_does_not_finish_assignment(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1, is_extended_answer=False)
        topic = Topic.objects.create(subject=subject, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        a = Assignment.objects.create(tutor=tutor, student=student, title="A", is_draft=False, is_completed=False, exam_format=ef)
        a.tasks.add(task)

        self.client.force_login(student)
        url = reverse("student_solve_assignment", args=[a.id])
        res = self.client.post(url, data={f"answer_{task.id}": "1"})  # action отсутствует
        # Можно редиректнуть обратно на страницу решения — важно, что вариант НЕ завершён.
        self.assertIn(res.status_code, (200, 302))

        a.refresh_from_db()
        self.assertFalse(a.is_completed)
