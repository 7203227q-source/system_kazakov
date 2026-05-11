from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, TaskType, User


class AdminExamStructureEditorTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="a", password="pass", role="admin")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")

        self.subj = Subject.objects.create(name="Математика")
        self.ef = ExamFormat.objects.create(subject=self.subj, name="ОГЭ математика", year=2026, is_active=True)
        self.tt1 = TaskType.objects.create(exam_format=self.ef, number=1, name="Тип 1", max_points=1)
        self.tt2 = TaskType.objects.create(exam_format=self.ef, number=2, name="Тип 2", max_points=1)

    def test_admin_can_open_page(self):
        self.client.login(username="a", password="pass")
        res = self.client.get(reverse("admin_exam_structure"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, self.ef.name)

    def test_non_admin_forbidden(self):
        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("admin_exam_structure"))
        self.assertEqual(res.status_code, 302)

    def test_admin_can_update_tasktype_names(self):
        self.client.login(username="a", password="pass")
        res = self.client.post(
            reverse("admin_exam_structure"),
            {
                "exam_format_id": str(self.ef.id),
                f"name_{self.tt1.id}": "Планиметрия",
                f"name_{self.tt2.id}": "Алгебра",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.tt1.refresh_from_db()
        self.tt2.refresh_from_db()
        self.assertEqual(self.tt1.name, "Планиметрия")
        self.assertEqual(self.tt2.name, "Алгебра")

