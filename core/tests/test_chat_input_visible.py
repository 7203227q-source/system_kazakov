from django.test import TestCase
from django.urls import reverse

from core.models import TutorStudentLink, User


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
