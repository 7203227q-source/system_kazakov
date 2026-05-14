import base64

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, OpenRouterModel, SpacedRepetition, Subject, SubjectAIConfig, Task, TaskType, TaskVariant, Topic, User


class StudentPracticeSrsExtendedUploadTests(TestCase):
    def test_srs_extended_task_shows_upload_controls(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        subj = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        SpacedRepetition.objects.create(student=student, task=task, next_review_date=timezone.now().date())

        # AI config нужна, чтобы кнопка проверки имела смысл (но UI должен быть и без неё)
        m = OpenRouterModel.objects.create(code="m1", label="M1", capabilities="vision", is_active=True)
        SubjectAIConfig.objects.create(subject=subj, photo_analysis_model=m)

        self.client.force_login(student)
        r = self.client.get(reverse("student_practice") + "?mode=srs")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertIn("Загрузите решение", html)
        self.assertIn("Проверить решение через ИИ", html)
        # Место для вывода вердикта ИИ после проверки
        self.assertIn("id=\"srs_ai_verdict\"", html)
