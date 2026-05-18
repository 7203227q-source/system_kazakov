import json

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


class StudentAssignmentAiFullReportTests(TestCase):
    def test_student_assignment_shows_recognized_solution_mistakes_verdict(self):
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

        Submission.objects.create(
            student=student,
            assignment=assignment,
            task=task,
            user_answer="",
            is_correct=False,
            primary_score=1,
            score=1,
            ai_feedback="Коротко",
            ai_recognized_solution="Распознано: x=1",
            ai_mistakes_json=json.dumps(["Ошибка 1"], ensure_ascii=False),
            ai_verdict_json=json.dumps(["Вердикт 1"], ensure_ascii=False),
        )

        self.client.force_login(student)
        res = self.client.get(f"/student/assignment/{assignment.id}/")
        self.assertEqual(res.status_code, 200)

        html = res.content.decode("utf-8", errors="ignore")
        for needle in [
            "Фото и вердикт ИИ",
            "Решение (как распознано)",
            "Распознано: x=1",
            "Ошибка 1",
            "Вердикт 1",
        ]:
            self.assertNotEqual(html.find(needle), -1, msg=f"Не найдено в HTML: {needle}")

    def test_student_assignment_shows_score_breakdown_section_when_present(self):
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

        Submission.objects.create(
            student=student,
            assignment=assignment,
            task=task,
            user_answer="",
            is_correct=False,
            primary_score=1,
            score=1,
            ai_feedback="Коротко",
            ai_recognized_solution="Распознано: x=1",
            ai_mistakes_json=json.dumps(["Ошибка 1"], ensure_ascii=False),
            ai_verdict_json=json.dumps(["Вердикт 1"], ensure_ascii=False),
            ai_score_breakdown_json=json.dumps(
                [{"label": "К1", "awarded": 1, "max": 3, "reason": "Нет обоснования"}],
                ensure_ascii=False,
            ),
        )
        sub = Submission.objects.get(student=student, assignment=assignment, task=task)
        self.assertIn("К1", sub.ai_score_breakdown_json or "")

        self.client.force_login(student)
        res = self.client.get(f"/student/assignment/{assignment.id}/")
        self.assertEqual(res.status_code, 200)

        html = res.content.decode("utf-8", errors="ignore")
        for needle in ["Снятие баллов", "К1", "1/3", "Нет обоснования"]:
            self.assertNotEqual(html.find(needle), -1, msg=f"Не найдено в HTML: {needle}")
