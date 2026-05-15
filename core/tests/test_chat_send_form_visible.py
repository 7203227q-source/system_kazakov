from django.test import TestCase
from django.urls import reverse

from core.models import User, TutorStudentLink


class ChatSendFormVisibleTests(TestCase):
    def test_tutor_sees_send_form_when_only_link_model_exists(self):
        tutor = User.objects.create_user(username="tutor1", password="pw", role="tutor")
        student = User.objects.create_user(username="student1", password="pw", role="student")
        TutorStudentLink.objects.create(tutor=tutor, student=student)

        self.client.force_login(tutor)
        response = self.client.get(reverse("chat_index"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="chat-input"')
        self.assertContains(response, 'id="send-btn"')

    def test_student_sees_send_form_when_only_link_model_exists(self):
        tutor = User.objects.create_user(username="tutor2", password="pw", role="tutor")
        student = User.objects.create_user(username="student2", password="pw", role="student")
        TutorStudentLink.objects.create(tutor=tutor, student=student)

        self.client.force_login(student)
        response = self.client.get(reverse("chat_index"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="chat-input"')
        self.assertContains(response, 'id="send-btn"')

