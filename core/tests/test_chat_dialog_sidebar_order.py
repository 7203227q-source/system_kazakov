from django.test import TestCase
from django.urls import reverse

from core.models import Message, TutorStudentLink, User


class ChatDialogSidebarOrderTests(TestCase):
    def test_active_dialog_is_pinned_to_top_for_tutor(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor", first_name="T")
        student_with_msgs = User.objects.create_user(username="s1", password="pass", role="student", first_name="S1")
        student_no_msgs = User.objects.create_user(username="s2", password="pass", role="student", first_name="S2")
        TutorStudentLink.objects.create(tutor=tutor, student=student_with_msgs)
        TutorStudentLink.objects.create(tutor=tutor, student=student_no_msgs)

        Message.objects.create(sender=student_with_msgs, receiver=tutor, content="hi")

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("chat_dialog", args=[student_no_msgs.id]))
        self.assertEqual(res.status_code, 200)

        html = res.content.decode("utf-8")
        pos_active = html.find("S2")
        pos_other = html.find("S1")
        self.assertTrue(pos_active != -1 and pos_other != -1)
        self.assertLess(pos_active, pos_other)

