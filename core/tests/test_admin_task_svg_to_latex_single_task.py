from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User


class SvgToLatexSingleTaskServiceTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ОГЭ", year=2026, is_active=True)
        self.topic = Topic.objects.create(subject=self.subject, name="T")
        self.tt = TaskType.objects.create(exam_format=self.exam_format, number=6, name="Тип 6", max_points=1)

        self.task = Task.objects.create(
            topic=self.topic,
            task_type=self.tt,
            correct_answer="1",
            difficulty=50,
            exam_points=1,
        )
        self.variant = TaskVariant.objects.create(
            task=self.task,
            theme="classic",
            content='<p>Формула: <img src="/formula/svg/123.svg" alt="x^2"></p>',
            solution='<p>Решение: <img src="/formula/svg/456.svg" alt="\\frac{1}{2}"></p>',
        )

    def test_convert_svg_to_latex_for_task_dry_run_does_not_modify_variant(self):
        from core.services_svg_to_latex import convert_svg_to_latex_for_task

        report = convert_svg_to_latex_for_task(task_id=self.task.id, theme="classic", dry_run=True)

        self.variant.refresh_from_db()
        self.assertIn("<img", self.variant.content)
        self.assertIn("<img", self.variant.solution)
        self.assertGreater(report.get("replaced", 0), 0)
        self.assertIn("$", report["new_content"])
        self.assertIn("$", report["new_solution"])

    def test_convert_svg_to_latex_for_task_apply_modifies_variant(self):
        from core.services_svg_to_latex import convert_svg_to_latex_for_task

        report = convert_svg_to_latex_for_task(task_id=self.task.id, theme="classic", dry_run=False)
        self.assertGreater(report.get("replaced", 0), 0)

        self.variant.refresh_from_db()
        self.assertNotIn("<img", self.variant.content)
        self.assertNotIn("<img", self.variant.solution)
        self.assertIn("$", self.variant.content)
        self.assertIn("$", self.variant.solution)


class SvgToLatexSingleTaskAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(username="admin", password="pass", email="a@a.ru")

        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subject, name="T")
        tt = TaskType.objects.create(exam_format=exam_format, number=6, name="Тип 6", max_points=1)
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=50, exam_points=1)
        self.variant = TaskVariant.objects.create(
            task=self.task,
            theme="classic",
            content='<p>Формула: <img src="/formula/svg/123.svg" alt="x^2"></p>',
            solution='<p>Решение: <img src="/formula/svg/456.svg" alt="\\frac{1}{2}"></p>',
        )

        self.client.force_login(self.admin_user)

    def test_admin_svg_to_latex_preview_does_not_modify_db(self):
        url = f"/admin/core/task/{self.task.id}/svg-to-latex-preview/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        self.variant.refresh_from_db()
        self.assertIn("<img", self.variant.content)

    def test_admin_svg_to_latex_apply_modifies_db(self):
        url = f"/admin/core/task/{self.task.id}/svg-to-latex-apply/"
        res = self.client.post(url, data={}, follow=False)
        self.assertIn(res.status_code, (302, 303))

        self.variant.refresh_from_db()
        self.assertNotIn("<img", self.variant.content)
        self.assertIn("$", self.variant.content)
