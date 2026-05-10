from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User


class TutorAssignmentExamFormatFilterTests(TestCase):
    def test_assignment_uses_selected_exam_format_only(self):
        tutor = User.objects.create_user(username="tutor2", password="pass", role="tutor")
        student = User.objects.create_user(username="student2", password="pass", role="student")
        tutor.students.add(student)
        self.client.login(username="tutor2", password="pass")

        subject = Subject.objects.create(name="Математика")
        ef_ege = ExamFormat.objects.create(subject=subject, name="ЕГЭ математика профиль", year=2026, is_active=True)
        ef_oge = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания из Открытого Банка")

        t_ege = TaskType.objects.create(exam_format=ef_ege, number=6, name="Тип 6", max_points=1)
        t_oge = TaskType.objects.create(exam_format=ef_oge, number=6, name="Тип 6", max_points=1)

        task_ege = Task.objects.create(topic=topic, task_type=t_ege, subtype_tag="x", correct_answer="1", difficulty=50, exam_points=1)
        task_oge = Task.objects.create(topic=topic, task_type=t_oge, subtype_tag="x", correct_answer="1", difficulty=50, exam_points=1)
        TaskVariant.objects.create(task=task_ege, theme="classic", content="x", solution="y")
        TaskVariant.objects.create(task=task_oge, theme="classic", content="x", solution="y")

        post = {
            "student_id": str(student.id),
            "exam_format": str(ef_ege.id),
            f"type_count_{t_ege.id}": "1",
            "subtype_checked_1": "on",
            "subtype_name_1": "x",
            "subtype_type_1": str(t_ege.id),
        }
        res = self.client.post(reverse("tutor_create_assignment"), post)
        self.assertEqual(res.status_code, 302)

        from core.models import Assignment

        assignment = Assignment.objects.latest("id")
        tasks = list(assignment.tasks.select_related("task_type").all())
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].task_type.exam_format_id, ef_ege.id)

