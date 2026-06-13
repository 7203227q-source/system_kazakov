from django.test import TestCase
from django.urls import reverse

from core.models import Subject, Task, TaskErrorReport, Topic, User


class AdminTaskErrorReportsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="a", password="pass", role="admin")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        subject = Subject.objects.create(name="Математика")
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, correct_answer="1", exam_points=1)
        self.report = TaskErrorReport.objects.create(
            task=task,
            reported_by=self.tutor,
            reporter_role="tutor",
            source="tutor_history",
            status="new",
        )

    def test_requires_admin(self):
        self.client.force_login(self.tutor)
        res = self.client.get(reverse("admin_task_error_reports"))
        self.assertIn(res.status_code, (302, 403))

    def test_admin_can_open_list_page(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("admin_task_error_reports"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Ошибки")
        self.assertContains(res, str(self.report.id))

    def test_admin_can_open_detail_page(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("admin_task_error_report_detail", args=[self.report.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, f"Task {self.report.task_id}")
        self.assertContains(res, "Сохранить статус")

    def test_admin_can_update_status(self):
        self.client.force_login(self.admin)
        res = self.client.post(
            reverse("admin_task_error_report_update", args=[self.report.id]),
            {"status": "resolved"},
        )
        self.assertEqual(res.status_code, 302)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "resolved")

    def test_admin_templates_include_errors_menu_link(self):
        self.client.force_login(self.admin)
        pages = [
            reverse("admin_dashboard"),
            reverse("admin_exam_structure"),
            reverse("admin_reshuege_import"),
            reverse("admin_system"),
            reverse("admin_openrouter_balance"),
        ]

        for url in pages:
            with self.subTest(url=url):
                res = self.client.get(url)
                self.assertEqual(res.status_code, 200)
                self.assertContains(res, reverse("admin_task_error_reports"))
                self.assertContains(res, "Ошибки")
