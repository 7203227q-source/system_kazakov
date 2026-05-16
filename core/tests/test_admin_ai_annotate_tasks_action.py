import os
from unittest import mock

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic


class AdminAiAnnotateTasksActionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_superuser(username="admin", password="pass", email="a@a.ru")

        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ОГЭ", year=2026, is_active=True)
        self.topic = Topic.objects.create(subject=self.subject, name="T")
        self.tt = TaskType.objects.create(exam_format=self.exam_format, number=1, name="Тип 1", max_points=1)

        self.tasks = []
        for i in range(30):
            t = Task.objects.create(
                topic=self.topic,
                task_type=self.tt,
                correct_answer="1",
                difficulty=50,
                exam_points=1,
            )
            TaskVariant.objects.create(task=t, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
            self.tasks.append(t)

        self.rf = RequestFactory()

    def _make_request(self):
        # Эмулируем запуск action с фильтром по exam_format через querystring.
        req = self.rf.post(f"/admin/core/task/?task_type__exam_format__id__exact={self.exam_format.id}")
        req.user = self.admin_user
        # messages framework for admin actions
        setattr(req, "session", self.client.session)
        messages = FallbackStorage(req)
        setattr(req, "_messages", messages)
        return req

    def test_admin_action_annotates_next_25_tasks_by_filter(self):
        os.environ["OPENROUTER_API_KEY"] = "dummy_key"

        # Подменяем вызов OpenRouter: всегда возвращаем difficulty_raw=80 и пустые теги.
        def _fake_post(*args, **kwargs):
            class _Resp:
                status_code = 200

                def json(self):
                    return {
                        "choices": [
                            {"message": {"content": '{"difficulty_raw":80,"methods":[],"properties":[],"topics":[]}'}}  # noqa: E501
                        ]
                    }

            return _Resp()

        with mock.patch("core.services_task_ai_annotation.requests.post", side_effect=_fake_post):
            # Создаём TaskAdmin заново, чтобы подхватить actions из core.admin
            from core.admin import TaskAdmin  # noqa: WPS433

            ma = TaskAdmin(Task, admin.site)
            req = self._make_request()

            # queryset, который даёт Django admin, здесь не важен — action должен работать по фильтру.
            ma.ai_annotate_difficulty_filtered_25(req, Task.objects.none())

        annotated = Task.objects.filter(task_type__exam_format=self.exam_format, ai_difficulty_raw__isnull=False)
        self.assertEqual(annotated.count(), 25)
        self.assertTrue(annotated.filter(ai_difficulty_raw=80).exists())

