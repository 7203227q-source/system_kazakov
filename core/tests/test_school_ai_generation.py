import os
from unittest.mock import patch

from django.contrib import admin
from django.test import RequestFactory, TestCase

from core.models import (
    CurriculumTopic,
    CurriculumUnit,
    LearningTaskType,
    LearningTrack,
    OpenRouterModel,
    SchoolTaskMeta,
    Subject,
    SubjectAIConfig,
    Task,
    Topic,
    User,
)
from core.services_school_ai import generate_school_task_draft


class SchoolAIGenerationTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.model = OpenRouterModel.objects.create(
            code="openai/gpt-4o-mini",
            label="GPT-4o mini",
            is_active=True,
        )
        SubjectAIConfig.objects.create(
            subject=self.subject,
            task_regen_text_model=self.model,
        )
        self.track = LearningTrack.objects.create(
            subject=self.subject,
            mode="school",
            grade=7,
            title="Математика, 7 класс",
        )
        self.unit = CurriculumUnit.objects.create(
            learning_track=self.track,
            title="Уравнения",
            position=1,
        )
        self.curriculum_topic = CurriculumTopic.objects.create(
            unit=self.unit,
            title="Линейные уравнения",
            position=1,
            is_required=True,
        )
        self.learning_type = LearningTaskType.objects.create(
            learning_track=self.track,
            code="linear-basic",
            name="Уравнение в одно действие",
            default_max_points=1,
            is_extended_answer=False,
        )
        self.tutor = User.objects.create_user(username="tutor", password="pass", role="tutor")

    def _fake_openrouter_post(self, *args, **kwargs):
        class _Resp:
            status_code = 200

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"content_html":"<p>Решите уравнение: x + 5 = 9</p>",'
                                    '"solution_html":"<p>x = 4</p>",'
                                    '"correct_answer":"4",'
                                    '"notes":"generated",'
                                    '"hints":["Перенесите 5 в другую часть"]}'
                                )
                            }
                        }
                    ]
                }

        return _Resp()

    @patch("core.services_school_ai.requests.post")
    def test_generate_school_task_draft_creates_draft_meta_and_provenance(self, mocked_post):
        os.environ["OPENROUTER_API_KEY"] = "dummy_key"
        mocked_post.side_effect = self._fake_openrouter_post

        task = generate_school_task_draft(
            actor=self.tutor,
            curriculum_topic=self.curriculum_topic,
            learning_task_type=self.learning_type,
            difficulty_level=2,
        )

        task.refresh_from_db()
        school_meta = task.school_meta

        self.assertEqual(school_meta.status, "draft")
        self.assertTrue(school_meta.generated_by_ai)
        self.assertEqual(school_meta.generated_by, self.tutor)
        self.assertEqual(task.correct_answer, "4")
        self.assertEqual(task.exam_points, 1)
        self.assertEqual(task.topic.subject, self.subject)
        self.assertEqual(task.topic.name, "Линейные уравнения")
        self.assertEqual(task.variants.get(theme="classic").content, "<p>Решите уравнение: x + 5 = 9</p>")
        self.assertEqual(task.variants.get(theme="classic").solution, "<p>x = 4</p>")
        self.assertEqual(
            school_meta.generation_notes,
            {
                "provider": "openrouter",
                "model": "openai/gpt-4o-mini",
                "difficulty_level": 2,
                "hints": ["Перенесите 5 в другую часть"],
                "notes": "generated",
            },
        )

    def test_admin_action_publishes_school_drafts(self):
        legacy_topic = Topic.objects.create(subject=self.subject, name="Черновики")
        draft_task = Task.objects.create(
            topic=legacy_topic,
            correct_answer="1",
            difficulty=25,
            exam_points=1,
        )
        school_meta = SchoolTaskMeta.objects.create(
            task=draft_task,
            learning_track=self.track,
            curriculum_topic=self.curriculum_topic,
            learning_task_type=self.learning_type,
            difficulty_level=1,
            status="draft",
            generated_by_ai=True,
            generated_by=self.tutor,
            generation_notes={"provider": "openrouter"},
        )

        admin_user = User.objects.create_superuser(username="admin", password="pass", email="admin@example.com")
        request = RequestFactory().post("/admin/core/schooltaskmeta/")
        request.user = admin_user

        from core.admin import SchoolTaskMetaAdmin

        model_admin = SchoolTaskMetaAdmin(SchoolTaskMeta, admin.site)
        model_admin.publish_drafts(request, SchoolTaskMeta.objects.filter(pk=school_meta.pk))

        school_meta.refresh_from_db()
        self.assertEqual(school_meta.status, "published")
