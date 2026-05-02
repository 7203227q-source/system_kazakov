from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Topic, TaskType, Task, TaskVariant, User


class TaskBankPurgeTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(
            subject=self.subject, name="ЕГЭ Профиль", year=2026, is_active=True
        )
        self.topic = Topic.objects.create(subject=self.subject, name="Задания из Открытого Банка")
        self.type7 = TaskType.objects.create(exam_format=self.exam_format, number=7, name="Тип 7", max_points=1)
        self.type8 = TaskType.objects.create(exam_format=self.exam_format, number=8, name="Тип 8", max_points=1)

        self.admin = User.objects.create_user(username="admin", password="1", role="admin")
        self.tutor = User.objects.create_user(username="tutor", password="1", role="tutor")

        t1 = Task.objects.create(
            topic=self.topic,
            task_type=self.type7,
            subtype_tag="A",
            difficulty=50,
            correct_answer="1",
            exam_points=1,
        )
        TaskVariant.objects.create(task=t1, theme="classic", content="<p>x</p>", solution="")

        t2 = Task.objects.create(
            topic=self.topic,
            task_type=self.type8,
            subtype_tag="B",
            difficulty=50,
            correct_answer="2",
            exam_points=1,
        )
        TaskVariant.objects.create(task=t2, theme="classic", content="<p>y</p>", solution="")

        self.url = reverse("tutor_task_purge")

    def test_non_admin_forbidden(self):
        self.client.login(username="tutor", password="1")
        res = self.client.post(self.url, {"action": "purge_all", "confirm": "DELETE ALL"})
        self.assertEqual(res.status_code, 403)

    def test_admin_requires_confirmation_phrase(self):
        self.client.login(username="admin", password="1")
        res = self.client.post(self.url, {"action": "purge_all", "confirm": "WRONG"})
        self.assertEqual(res.status_code, 302)
        self.assertEqual(Task.objects.count(), 2)

    def test_admin_purge_by_exam_format(self):
        self.client.login(username="admin", password="1")
        res = self.client.post(
            self.url,
            {
                "action": "purge_exam_format",
                "exam_format_id": str(self.exam_format.id),
                "confirm": "DELETE",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(Task.objects.count(), 0)

    def test_admin_purge_by_exam_format_and_type_number(self):
        t3 = Task.objects.create(
            topic=self.topic,
            task_type=self.type7,
            subtype_tag="C",
            difficulty=50,
            correct_answer="3",
            exam_points=1,
        )
        TaskVariant.objects.create(task=t3, theme="classic", content="<p>z</p>", solution="")

        self.client.login(username="admin", password="1")
        res = self.client.post(
            self.url,
            {
                "action": "purge_exam_format_type",
                "exam_format_id": str(self.exam_format.id),
                "type_number": "7",
                "confirm": "DELETE",
            },
        )
        self.assertEqual(res.status_code, 302)
        remaining = list(Task.objects.values_list("task_type__number", flat=True))
        self.assertEqual(sorted(remaining), [8])

