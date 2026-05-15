from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import (
    Assignment,
    ExamFormat,
    Subject,
    Submission,
    SubmissionComment,
    Task,
    TaskType,
    TaskVariant,
    Topic,
    User,
)


class TutorDashboardCommentsAndLimitsTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="tutor1", password="pw", role="tutor")
        self.student = User.objects.create_user(username="student1", password="pw", role="student")
        self.tutor.students.add(self.student)

        self.subject = Subject.objects.create(name="Физика")
        self.ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ физика", year=2026, is_active=True)
        self.tt = TaskType.objects.create(exam_format=self.ef, number=1, name="Тест", max_points=2, is_extended_answer=False)
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")

    def test_dashboard_shows_only_10_completed_assignments_and_comments_list(self):
        now = timezone.now()

        # 12 завершённых вариантов
        for i in range(12):
            a = Assignment.objects.create(
                tutor=self.tutor,
                student=self.student,
                title=f"Done {i+1}",
                is_draft=False,
                is_deleted=False,
                is_completed=True,
            )
            Assignment.objects.filter(id=a.id).update(created_at=now - timedelta(minutes=(12 - i)))

        # Создаём submission + 2 комментария, чтобы проверить список
        task = Task.objects.create(topic=self.topic, task_type=self.tt, correct_answer="1", exam_points=2)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        a0 = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="Active A",
            is_draft=False,
            is_deleted=False,
            is_completed=False,
        )
        a0.tasks.add(task)
        sub = Submission.objects.create(student=self.student, assignment=a0, task=task, user_answer="1", is_correct=True, score=2)

        SubmissionComment.objects.create(
            submission=sub,
            author=self.student,
            author_role="student",
            text="Первый вопрос",
            seen_by_tutor_at=None,
        )
        SubmissionComment.objects.create(
            submission=sub,
            author=self.tutor,
            author_role="tutor",
            text="Ответ репетитора",
            seen_by_tutor_at=timezone.now(),
        )

        self.client.force_login(self.tutor)
        res = self.client.get("/tutor/", {"student_id": str(self.student.id)})
        self.assertEqual(res.status_code, 200)

        html = res.content.decode("utf-8", errors="ignore")

        # Лимит: показываем последние 10 (Done 3..Done 12)
        self.assertNotEqual(html.find("Done 12"), -1, msg=f"Не найден Done 12, idx={html.find('Done')}")
        self.assertNotEqual(html.find("Done 3"), -1, msg=f"Не найден Done 3, idx={html.find('Done')}")
        self.assertEqual(html.find(">Done 2<"), -1, msg="Done 2 не должен отображаться (лимит 10)")
        self.assertEqual(html.find(">Done 1<"), -1, msg="Done 1 не должен отображаться (лимит 10)")

        # Комментарии выводятся списком
        self.assertNotEqual(html.find("Комментарии"), -1, msg="Не найден заголовок Комментарии")
        self.assertNotEqual(html.find("Первый вопрос"), -1, msg="Не найден комментарий ученика")
        self.assertNotEqual(html.find("Ответ репетитора"), -1, msg="Не найден комментарий репетитора")
        self.assertNotEqual(html.find("новое"), -1, msg="Не найден бейдж 'новое' для непрочитанного комментария")
