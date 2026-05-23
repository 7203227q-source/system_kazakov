from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User


class ChatIndexAutoselectsDialogTests(TestCase):
    def test_chat_index_shows_input_even_without_dialogs(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")

        self.client.login(username="t", password="pass")
        r = self.client.get(reverse("chat_index"))
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="chat-input"', r.content.decode("utf-8"))

    def test_chat_index_autoselects_first_dialog(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        student.tutors.add(tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subj, name="T")
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1, is_extended_answer=False)
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        a = Assignment.objects.create(tutor=tutor, student=student, title="A", is_draft=False)
        a.tasks.add(task)

        self.client.login(username="t", password="pass")
        r = self.client.get(reverse("chat_index"))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertIn("chat-input", html)
