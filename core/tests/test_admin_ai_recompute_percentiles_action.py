from django.contrib import admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from core.models import ExamFormat, Subject, Task, TaskType, Topic, User


class AdminAiRecomputePercentilesActionTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(username="admin", password="pass", email="a@a.ru")

        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ОГЭ", year=2026, is_active=True)
        self.topic = Topic.objects.create(subject=self.subject, name="T")
        self.tt = TaskType.objects.create(exam_format=self.exam_format, number=1, name="Тип 1", max_points=1)

        # три задачи с разной raw-сложностью
        for raw in (10, 50, 90):
            Task.objects.create(
                topic=self.topic,
                task_type=self.tt,
                correct_answer="1",
                difficulty=50,
                exam_points=1,
                ai_difficulty_raw=raw,
                ai_annotation_version="v1",
            )

        self.rf = RequestFactory()

    def _make_request(self):
        req = self.rf.post(f"/admin/core/task/?task_type__exam_format__id__exact={self.exam_format.id}")
        req.user = self.admin_user
        setattr(req, "session", {})
        messages = FallbackStorage(req)
        setattr(req, "_messages", messages)
        return req

    def test_admin_action_recomputes_percentiles_by_filter(self):
        from core.admin import TaskAdmin  # noqa: WPS433

        ma = TaskAdmin(Task, admin.site)
        req = self._make_request()

        # action должен брать queryset по фильтру и выставить процентили
        ma.ai_recompute_ai_percentiles_filtered(req, Task.objects.none())

        qs = Task.objects.filter(task_type__exam_format=self.exam_format).order_by("ai_difficulty_raw")
        pcts = list(qs.values_list("ai_difficulty_exam_percentile", flat=True))
        self.assertEqual(pcts, [0, 50, 100])

