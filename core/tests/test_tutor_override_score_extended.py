from django.test import TestCase

from core.models import (
    User,
    Subject,
    ExamFormat,
    TaskType,
    Topic,
    Task,
    TaskVariant,
    Assignment,
    Submission,
)


class TutorOverrideScoreExtendedTests(TestCase):
    def test_tutor_override_updates_primary_score_and_student_sees_it(self):
        tutor = User.objects.create_user(username="t1", password="pw", role="tutor")
        student = User.objects.create_user(username="s1", password="pw", role="student")
        tutor.students.add(student)

        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=25, name="Развёрнутая", max_points=3, is_extended_answer=True)
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="", exam_points=3)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        assignment = Assignment.objects.create(tutor=tutor, student=student, title="Вариант", is_draft=False, is_deleted=False)
        assignment.tasks.add(task)
        sub = Submission.objects.create(
            student=student,
            assignment=assignment,
            task=task,
            user_answer="",
            is_correct=False,
            primary_score=1,
            score=1,
            ai_feedback="ИИ поставил 1",
        )

        self.client.force_login(tutor)
        res = self.client.post(f"/api/tutor/submission/{sub.id}/override-score/", {"tutor_primary_score": "3"})
        self.assertEqual(res.status_code, 200)

        sub.refresh_from_db()
        self.assertEqual(sub.tutor_primary_score, 3)
        self.assertEqual(sub.primary_score, 3)
        self.assertEqual(sub.score, 3)
        self.assertTrue(sub.is_correct)

        # Ученик должен видеть обновлённый балл на странице решения варианта
        self.client.force_login(student)
        res2 = self.client.get(f"/student/assignment/{assignment.id}/")
        self.assertEqual(res2.status_code, 200)
        self.assertContains(res2, "Оценено")
        self.assertContains(res2, "3")
