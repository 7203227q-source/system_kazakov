from django.test import TestCase
from django.urls import reverse

from core.models import Message, TutorStudentLink, User


class ChatNeedsReplyBadgeTests(TestCase):
    def test_tutor_sees_needs_reply_badge_when_last_message_from_student(self):
        tutor = User.objects.create_user(username="tutor1", password="pw", role="tutor")
        student = User.objects.create_user(username="student1", password="pw", role="student")
        TutorStudentLink.objects.create(tutor=tutor, student=student)

        Message.objects.create(sender=student, receiver=tutor, content="Привет", is_read=True)

        self.client.force_login(tutor)
        response = self.client.get(reverse("chat_index"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ждёт ответа")

    def test_tutor_does_not_see_needs_reply_badge_when_last_message_from_tutor(self):
        tutor = User.objects.create_user(username="tutor2", password="pw", role="tutor")
        student = User.objects.create_user(username="student2", password="pw", role="student")
        TutorStudentLink.objects.create(tutor=tutor, student=student)

        Message.objects.create(sender=student, receiver=tutor, content="Привет", is_read=True)
        Message.objects.create(sender=tutor, receiver=student, content="Ответил", is_read=True)

        self.client.force_login(tutor)
        response = self.client.get(reverse("chat_index"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Ждёт ответа")

