from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, Topic, User


class TutorAssignmentViewHidesTutorScoreForTestPartTests(TestCase):
    def test_does_not_show_tutor_score_block_for_test_part(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subj = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subj, name="T")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        # Тестовая часть
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1, is_extended_answer=False)
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        a = Assignment.objects.create(tutor=tutor, student=student, title="A", is_draft=False, exam_format=ef)
        a.tasks.add(task)
        Submission.objects.create(student=student, task=task, assignment=a, user_answer="1", is_correct=True, score=1)

        self.client.login(username="t", password="pass")
        r = self.client.get(reverse("tutor_assignment_view", args=[a.id]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertNotIn("Итог репетитора", html)

