import json

from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User


class TaskRegenerationTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ Профиль", year=2026, is_active=True)
        self.task_type = TaskType.objects.create(exam_format=self.exam_format, number=1, name="Планиметрия", max_points=1)
        self.topic = Topic.objects.create(subject=self.subject, name="Задания из Открытого Банка")

        self.task = Task.objects.create(
            fipi_id="T-1",
            topic=self.topic,
            task_type=self.task_type,
            subtype_tag="Прямоугольные треугольники",
            correct_answer="24",
            difficulty=50,
            exam_points=1,
        )
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Условие</p>", solution="<p>Решение</p>")

        self.admin_user = User.objects.create_user(username="admin_u", email="admin_u@example.com", password="pass", role="admin")
        self.tutor_user = User.objects.create_user(username="tutor_u", email="tutor_u@example.com", password="pass", role="tutor")

    def _reverse_or_fail(self, name, *args):
        try:
            return reverse(name, args=args)
        except Exception as e:
            self.fail(f"Missing url '{name}': {e}")

    def test_preview_endpoint_requires_admin(self):
        url = self._reverse_or_fail("admin_task_regen_preview", self.task.id)
        self.client.force_login(self.tutor_user)
        res = self.client.post(url, data=json.dumps({"mode": "full", "model": "test"}), content_type="application/json")
        self.assertIn(res.status_code, [302, 403])

    def test_admin_can_preview_regeneration(self):
        url = self._reverse_or_fail("admin_task_regen_preview", self.task.id)
        self.client.force_login(self.admin_user)
        res = self.client.post(url, data=json.dumps({"mode": "full", "model": "test"}), content_type="application/json")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertIn("preview", payload)

    def test_admin_can_apply_regeneration(self):
        url = self._reverse_or_fail("admin_task_regen_apply", self.task.id)
        self.client.force_login(self.admin_user)

        from core.models import OpenRouterModel, SubjectAIConfig
        model_obj = OpenRouterModel.objects.create(code="openai/gpt-4o-mini", label="GPT-4o mini")
        SubjectAIConfig.objects.create(subject=self.subject, task_regen_text_model=model_obj)

        try:
            from unittest.mock import patch
            with patch("core.openrouter_client.generate_task_regeneration") as mocked:
                mocked.return_value = {
                    "content_html": "<p>NEW</p>",
                    "solution_html": "<p>SOL</p>",
                    "correct_answer": "99",
                    "notes": "",
                }
                res = self.client.post(url, data=json.dumps({"mode": "full", "model": ""}), content_type="application/json")
                _, kwargs = mocked.call_args
                self.assertEqual(kwargs.get("model"), "openai/gpt-4o-mini")
        except Exception as e:
            self.fail(f"Missing OpenRouter integration stub: {e}")

        self.assertEqual(res.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.correct_answer, "99")

        try:
            from core.models import TaskGenerationLog
        except Exception as e:
            self.fail(f"Missing TaskGenerationLog model: {e}")
        self.assertEqual(TaskGenerationLog.objects.count(), 1)


class TaskBankFilteringTests(TestCase):
    def setUp(self):
        self.subject1 = Subject.objects.create(name="Математика")
        self.subject2 = Subject.objects.create(name="Физика")
        self.format1 = ExamFormat.objects.create(subject=self.subject1, name="ЕГЭ", year=2026, is_active=True)
        self.format2 = ExamFormat.objects.create(subject=self.subject2, name="ЕГЭ", year=2026, is_active=True)
        self.type1 = TaskType.objects.create(exam_format=self.format1, number=1, name="Тип 1", max_points=1)
        self.type2 = TaskType.objects.create(exam_format=self.format2, number=1, name="Тип 1", max_points=1)
        topic1 = Topic.objects.create(subject=self.subject1, name="Задания из Открытого Банка")
        topic2 = Topic.objects.create(subject=self.subject2, name="Задания из Открытого Банка")
        Task.objects.create(fipi_id="M1", topic=topic1, task_type=self.type1, correct_answer="1", difficulty=50, exam_points=1)
        Task.objects.create(fipi_id="P1", topic=topic2, task_type=self.type2, correct_answer="1", difficulty=50, exam_points=1)
        self.admin_user = User.objects.create_user(username="admin_f", email="admin_f@example.com", password="pass", role="admin")

    def test_admin_can_filter_task_bank_by_subject(self):
        self.client.force_login(self.admin_user)
        url = reverse("tutor_task_bank") + f"?subject={self.subject1.id}"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        try:
            tasks = list(res.context["tasks"])
        except Exception as e:
            self.fail(f"Task bank must provide tasks in context: {e}")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].fipi_id, "M1")
