import base64
import json
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, OpenRouterModel, Subject, SubjectAIConfig, Submission, Task, TaskType, TaskVariant, Topic, User


class AIFeedbackPersistedOnReloadTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=20, name="№20", max_points=2, is_extended_answer=True)
        topic = Topic.objects.create(subject=subj, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>SOLUTION</p>")

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=ef)
        self.assignment.tasks.add(self.task)

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        self.sub = Submission.objects.create(student=self.student, assignment=self.assignment, task=self.task, image_url=image)

        model_obj = OpenRouterModel.objects.create(code="google/gemini-2.0-flash", label="Gemini 2.0 Flash", capabilities="vision")
        SubjectAIConfig.objects.create(subject=subj, photo_analysis_model=model_obj)

    def test_feedback_visible_after_reload(self):
        os.environ["OPENROUTER_API_KEY"] = "test"
        dummy = {"choices": [{"message": {"content": json.dumps({"primary_score": 1, "is_correct": False, "feedback": "AI FEEDBACK"})}}]}

        from unittest.mock import patch
        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy

            self.client.login(username="s", password="pass")
            res = self.client.post(reverse("api_verify_with_ai", args=[self.sub.id]))
            self.assertEqual(res.status_code, 200)

        # reload assignment page
        page = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "AI FEEDBACK")

