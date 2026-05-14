import os
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse

from core.models import (
    Assignment,
    ExamFormat,
    OpenRouterModel,
    Subject,
    SubjectAIConfig,
    Task,
    TaskType,
    Topic,
    User,
    TaskVariant,
    WhiteboardSession,
)


class WhiteboardAiVerifyTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="tutor1", password="x", role="tutor")
        self.student = User.objects.create_user(username="student1", password="x", role="student")
        self.tutor.students.add(self.student)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(
            exam_format=ef,
            number=13,
            name="Развернутая",
            max_points=3,
            is_extended_answer=True,
        )
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="", difficulty=30, exam_points=3)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Условие</p>", solution="<p>Решение</p>")

        model = OpenRouterModel.objects.create(code="test-model", label="Test model")
        SubjectAIConfig.objects.create(subject=subj, photo_analysis_model=model)

        assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="Вариант", is_draft=False)
        assignment.tasks.add(task)
        self.session = WhiteboardSession.objects.create(
            student=self.student,
            tutor=self.tutor,
            assignment=assignment,
            task=task,
            snapshot_json='{"version":2,"objects":[]}',
        )

    def test_student_cannot_verify_ai(self):
        self.client.login(username="student1", password="x")
        url = reverse("whiteboard_verify_ai", args=[self.session.id])
        r = self.client.post(url, data={"image_data_url": "data:image/png;base64,AAAA"})
        self.assertEqual(r.status_code, 403)

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    @patch("core.views.requests.post")
    def test_tutor_can_verify_ai_and_result_saved(self, post: Mock):
        post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "choices": [
                    {
                        "message": {
                            "content": '{"primary_score": 2, "is_correct": false, "feedback": "- Ошибки: неверный знак\\\\n- Что исправить: ..."}'
                        }
                    }
                ]
            },
        )

        self.client.login(username="tutor1", password="x")
        url = reverse("whiteboard_verify_ai", args=[self.session.id])
        r = self.client.post(
            url,
            data='{"image_data_url":"data:image/png;base64,AAAA"}',
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(int(data.get("primary_score") or 0), 2)

        self.session.refresh_from_db()
        self.assertEqual(self.session.ai_score, 2)
        self.assertEqual(self.session.ai_max_score, 3)
        self.assertTrue(self.session.ai_feedback)

