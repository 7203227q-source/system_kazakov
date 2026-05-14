from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, Subject, Task, TaskType, TaskVariant, Topic, User


class StudentPracticeSrsModePersistsTests(TestCase):
    def test_result_next_link_preserves_srs_mode_and_title(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1, is_extended_answer=False)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        SpacedRepetition.objects.create(student=student, task=task, next_review_date=timezone.now().date())

        self.client.force_login(student)
        # GET: должен показать режим повторения
        r = self.client.get(reverse("student_practice") + "?mode=srs")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertIn("Повторить сегодня", html)

        token = self.client.session.get("practice_current", {}).get("token")
        self.assertTrue(token)

        # POST: результат и ссылка "Следующая задача" должны сохранить mode=srs
        res = self.client.post(
            reverse("student_practice"),
            data={"task_id": task.id, "answer": "1", "mode": "srs", "attempt_token": token},
        )
        self.assertEqual(res.status_code, 200)
        html2 = res.content.decode("utf-8")
        self.assertIn("?mode=srs", html2)

