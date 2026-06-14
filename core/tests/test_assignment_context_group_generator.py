from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskContextGroup, TaskType, Topic, User


class AssignmentContextGroupGeneratorTests(TestCase):
    def test_selecting_one_grouped_task_expands_to_all_tasks_in_context_group(self):
        tutor = User.objects.create_user(username="tutor_ctx", password="pass", role="tutor")
        student = User.objects.create_user(username="student_ctx", password="pass", role="student")
        tutor.students.add(student)
        self.client.login(username="tutor_ctx", password="pass")

        subject = Subject.objects.create(name="Английский язык")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ английский", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subject, name="Аудирование")

        type_6 = TaskType.objects.create(exam_format=exam_format, number=6, name="Тип 6", max_points=1)
        type_7 = TaskType.objects.create(exam_format=exam_format, number=7, name="Тип 7", max_points=1)

        group = TaskContextGroup.objects.create(
            source="reshuege",
            group_key="audio-group-1",
            subject=subject,
            exam_format=exam_format,
            title="Общий аудиоблок",
        )

        selected_anchor = Task.objects.create(
            topic=topic,
            task_type=type_6,
            subtype_tag="grouped",
            context_group=group,
            correct_answer="1",
            difficulty=10,
            exam_points=1,
        )
        sibling = Task.objects.create(
            topic=topic,
            task_type=type_7,
            subtype_tag="grouped",
            context_group=group,
            correct_answer="2",
            difficulty=15,
            exam_points=1,
        )

        response = self.client.post(
            reverse("tutor_create_assignment"),
            {
                "student_id": str(student.id),
                "exam_format": str(exam_format.id),
                f"type_count_{type_6.id}": "1",
                "subtype_checked_1": "on",
                "subtype_name_1": "grouped",
                "subtype_type_1": str(type_6.id),
            },
        )
        self.assertEqual(response.status_code, 302)

        from core.models import Assignment

        assignment = Assignment.objects.latest("id")
        self.assertCountEqual(
            list(assignment.tasks.values_list("id", flat=True)),
            [selected_anchor.id, sibling.id],
        )
