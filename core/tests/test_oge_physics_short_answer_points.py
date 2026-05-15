from django.test import TestCase
from django.urls import reverse

from core.models import Subject, ExamFormat, TaskType, Topic, Task, TaskVariant, User, Assignment, Submission


class OgePhysicsShortAnswerPointsTests(TestCase):
    def test_check_endpoint_sets_score_to_tasktype_max_points(self):
        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ физика (тест)", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=12, name="Тест (2 балла)", max_points=2, is_extended_answer=False)

        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="42", exam_points=1)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        student = User.objects.create_user(username="s1", password="pw", role="student")
        tutor = User.objects.create_user(username="t1", password="pw", role="tutor")
        assignment = Assignment.objects.create(tutor=tutor, student=student, title="Вариант", is_draft=False)
        assignment.tasks.add(task)

        self.client.force_login(student)
        url = reverse("student_check_assignment_task", args=[assignment.id, task.id])
        res = self.client.post(url, {"answer": "42"})
        self.assertEqual(res.status_code, 200)

        sub = Submission.objects.get(student=student, assignment=assignment, task=task)
        self.assertTrue(sub.is_correct)
        self.assertEqual(int(sub.score or 0), 2)

