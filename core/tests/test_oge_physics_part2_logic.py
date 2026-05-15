from django.test import TestCase
from django.urls import reverse

from core.models import Subject, ExamFormat, TaskType, Topic, Task, TaskVariant, User, Assignment


class OGEPhysicsPart2LogicTests(TestCase):
    def test_short_answer_2_points_is_not_part2(self):
        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="Тест (2 балла)", max_points=2)

        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", exam_points=2)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        student = User.objects.create_user(username="s1", password="pw", role="student")
        tutor = User.objects.create_user(username="t1", password="pw", role="tutor")
        assignment = Assignment.objects.create(tutor=tutor, student=student, title="Вариант")
        assignment.tasks.add(task)

        self.client.force_login(student)
        res = self.client.get(reverse("student_solve_assignment", args=[assignment.id]))
        self.assertEqual(res.status_code, 200)

        # Если бы работала эвристика task.exam_points > 1, то требовалось бы фото и появлялся бы QR-блок.
        self.assertNotContains(res, "Загрузите решение с телефона")

    def test_summary_counts_2_points_short_answer(self):
        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(
            exam_format=ef,
            number=12,
            name="Тест (2 балла)",
            max_points=2,
            is_extended_answer=False,
        )

        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="42", exam_points=2)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        student = User.objects.create_user(username="s2", password="pw", role="student")
        tutor = User.objects.create_user(username="t2", password="pw", role="tutor")
        assignment = Assignment.objects.create(tutor=tutor, student=student, title="Вариант")
        assignment.tasks.add(task)

        # имитируем завершённый вариант
        from core.models import Submission
        Submission.objects.create(student=student, task=task, assignment=assignment, user_answer="42", is_correct=True, score=2)
        assignment.is_completed = True
        assignment.save()

        self.client.force_login(student)
        res = self.client.get(reverse("student_assignment_summary", args=[assignment.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, ">2<span")
