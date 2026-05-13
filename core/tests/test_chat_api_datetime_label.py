from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse

from core.models import Message, TutorStudentLink, User


class ChatApiDatetimeLabelTests(TestCase):
    def test_api_returns_created_at_label_in_moscow_time(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        TutorStudentLink.objects.create(tutor=tutor, student=student)

        msg = Message.objects.create(sender=student, receiver=tutor, content="hi")
        Message.objects.filter(id=msg.id).update(created_at=datetime(2026, 5, 13, 6, 5, tzinfo=ZoneInfo("UTC")))

        from unittest.mock import patch
        with patch("core.datetime_ui.timezone.now") as now:
            now.return_value = datetime(2026, 5, 13, 6, 10, tzinfo=ZoneInfo("UTC"))

            self.client.login(username="t", password="pass")
            res = self.client.get(reverse("api_get_messages", args=[student.id]) + "?after=0")

        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertTrue(payload["messages"])
        self.assertEqual(payload["messages"][0]["created_at_label"], "сегодня 09:05")

