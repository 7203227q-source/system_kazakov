from django.test import TestCase
from django.urls import reverse

from core.models import Subject, Task, TaskErrorReport, Topic, User


class AdminSchoolProgramTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pass", role="admin")
        self.tutor = User.objects.create_user(username="tutor", password="pass", role="tutor")
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
        res = self.client.get(reverse("admin_school_program"))
        self.assertIn(res.status_code, (302, 403))

    def test_admin_can_open_school_program_page(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("admin_school_program"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Школьная программа")
        self.assertContains(res, "Быстрый старт")
        self.assertContains(res, "/admin/core/learningtrack/")
        self.assertContains(res, "/admin/core/curriculumtopic/")
        self.assertContains(res, "/admin/core/schooltaskmeta/")

    def test_existing_platform_admin_pages_include_school_program_menu_link(self):
        self.client.force_login(self.admin)
        pages = [
            reverse("admin_dashboard"),
            reverse("admin_exam_structure"),
            reverse("admin_reshuege_import"),
            reverse("admin_system"),
            reverse("admin_openrouter_balance"),
            reverse("admin_task_error_reports"),
            reverse("admin_task_error_report_detail", args=[self.report.id]),
        ]
        for url in pages:
            with self.subTest(url=url):
                res = self.client.get(url)
                self.assertEqual(res.status_code, 200)
                self.assertContains(res, reverse("admin_school_program"))
                self.assertContains(res, "Школьная программа")
