import json
import os
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import (
    Assignment,
    ExamFormat,
    OpenRouterModel,
    Subject,
    SubjectAIConfig,
    Submission,
    Task,
    TaskType,
    TaskVariant,
    Topic,
    User,
)


class TutorVerifyAiCooldownTests(TestCase):
    def setUp(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor.students.add(self.student)

        subj = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subj, name="T")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)

        model = OpenRouterModel.objects.create(code="test-model", label="Test", is_active=True)
        SubjectAIConfig.objects.create(subject=subj, photo_analysis_model=model)

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=ef)
        self.assignment.tasks.add(self.task)
        # минимальный валидный PNG (1x1)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xa6\x18\xdd\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        self.sub = Submission.objects.create(student=self.student, task=self.task, assignment=self.assignment, image_url=image)

    def test_tutor_verify_ai_has_cooldown(self):
        self.client.login(username="t", password="pass")
        url = reverse("api_tutor_verify_with_ai", args=[self.sub.id])

        dummy_response = {
            "choices": [
                {"message": {"content": json.dumps({"primary_score": 1, "is_correct": False, "feedback": "ok"})}}
            ]
        }
        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response

            r1 = self.client.post(url)
            self.assertEqual(r1.status_code, 200, r1.content)
            r2 = self.client.post(url)
            self.assertEqual(r2.status_code, 429)

    def test_tutor_verify_ai_uses_two_step_when_solution_exists(self):
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        check_model = OpenRouterModel.objects.create(code="check-model", label="Check", is_active=True)
        SubjectAIConfig.objects.update(solution_check_model=check_model)

        self.client.login(username="t", password="pass")
        url = reverse("api_tutor_verify_with_ai", args=[self.sub.id])

        recognition = {
            "photo_valid": True,
            "photo_valid_reason": "",
            "recognition_confidence": 0.8,
            "recognized_solution": "x=1",
        }
        grading = {
            "primary_score": 1,
            "is_correct": False,
            "mistakes": ["m1"],
            "verdict": ["v1"],
            "feedback": "",
        }
        dummy_response_1 = {"choices": [{"message": {"content": json.dumps(recognition, ensure_ascii=False)}}]}
        dummy_response_2 = {"choices": [{"message": {"content": json.dumps(grading, ensure_ascii=False)}}]}

        with patch("core.views.requests.post") as post:
            class R:
                def __init__(self, payload):
                    self.status_code = 200
                    self._payload = payload

                def json(self):
                    return self._payload

            post.side_effect = [R(dummy_response_1), R(dummy_response_2)]

            r1 = self.client.post(url)

        self.assertEqual(r1.status_code, 200, r1.content)
        data = r1.json()
        self.assertEqual(data["recognized_solution"], recognition["recognized_solution"])
        self.assertEqual(data["mistakes"], grading["mistakes"])
        self.assertTrue(
            any("Неуверенность распознавания" in (v or "") for v in (data.get("verdict") or [])),
            msg="Ожидали строку про неуверенность распознавания в verdict",
        )
        self.assertEqual(data.get("model"), "check-model")
        self.assertEqual(post.call_count, 2)

    def test_tutor_verify_ai_passes_review_context_to_srs_processing(self):
        self.client.login(username="t", password="pass")
        url = reverse("api_tutor_verify_with_ai", args=[self.sub.id])

        dummy_response = {
            "choices": [
                {"message": {"content": json.dumps({"primary_score": 1, "is_correct": False, "feedback": "ok"})}}
            ]
        }

        with patch("core.views.requests.post") as post, patch("core.views.process_task_submission") as process_task_submission:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response

            response = self.client.post(url)

        self.assertEqual(response.status_code, 200, response.content)
        process_task_submission.assert_called_once_with(
            self.student,
            self.task,
            1,
            active_time_seconds=60,
            attempt_count=1,
        )
