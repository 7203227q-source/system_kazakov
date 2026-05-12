from django.test import TestCase
from django.urls import reverse

from core.models import TutorStudentLink, User
from core.models import Assignment


class ChatInputVisibleTests(TestCase):
    def test_tutor_sees_chat_input_when_link_exists(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        TutorStudentLink.objects.create(tutor=tutor, student=student)

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("chat_dialog", args=[student.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'id="chat-input"')

    def test_student_sees_chat_input_when_link_exists(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        TutorStudentLink.objects.create(tutor=tutor, student=student)

        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("chat_dialog", args=[tutor.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'id="chat-input"')

    def test_student_sees_chat_input_when_m2m_exists(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        student.tutors.add(tutor)

        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("chat_dialog", args=[tutor.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'id="chat-input"')

    def test_chat_input_visible_when_assignment_exists(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        Assignment.objects.create(tutor=tutor, student=student, title="Вариант 1")

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("chat_dialog", args=[student.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'id="chat-input"')

        self.client.logout()
        self.client.login(username="s", password="pass")
        res2 = self.client.get(reverse("chat_dialog", args=[tutor.id]))
        self.assertEqual(res2.status_code, 200)
        self.assertContains(res2, 'id="chat-input"')
