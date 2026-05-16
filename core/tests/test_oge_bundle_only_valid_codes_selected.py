from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User


class OgeBundleOnlyValidCodesSelectedTests(TestCase):
    def test_generator_does_not_use_invalid_bundle_codes(self):
        tutor = User.objects.create_user(username="tutor", password="pass", role="tutor")
        student = User.objects.create_user(username="student", password="pass", role="student")
        tutor.students.add(student)
        self.client.login(username="tutor", password="pass")

        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        topic = Topic.objects.create(subject=subject, name="T")

        task_types = {}
        for n in range(1, 7):
            task_types[n] = TaskType.objects.create(exam_format=exam_format, number=n, name=f"Тип {n}", max_points=1)

        # Невалидная связка: нет задачи №4.
        bad_bundle = "B_BAD"
        for n in (1, 2, 3, 5):
            task = Task.objects.create(
                topic=topic,
                task_type=task_types[n],
                subtype_tag="block",
                bundle_code=bad_bundle,
                correct_answer="1",
                difficulty=50,
                exam_points=1,
            )
            TaskVariant.objects.create(task=task, theme="classic", content="x", solution="y")

        # Обычная задача вне связок (чтобы вариант мог собраться даже без валидных bundle).
        t6 = Task.objects.create(
            topic=topic,
            task_type=task_types[6],
            subtype_tag="other",
            correct_answer="1",
            difficulty=50,
            exam_points=1,
        )
        TaskVariant.objects.create(task=t6, theme="classic", content="x", solution="y")

        t1 = task_types[1]
        post = {
            "student_id": str(student.id),
            "exam_format": str(exam_format.id),
            # просим одну связку 1–5
            f"type_count_{t1.id}": "1",
            "subtype_checked_1": "on",
            "subtype_name_1": "block",
            "subtype_type_1": str(t1.id),
            # и одну обычную задачу №6
            f"type_count_{task_types[6].id}": "1",
            "subtype_checked_2": "on",
            "subtype_name_2": "other",
            "subtype_type_2": str(task_types[6].id),
        }
        res = self.client.post(reverse("tutor_create_assignment"), post)
        self.assertEqual(res.status_code, 302)

        from core.models import Assignment

        assignment = Assignment.objects.latest("id")
        # До фикса сюда попадала невалидная связка (4 задачи) + тип 6.
        self.assertEqual(assignment.tasks.count(), 1)
        self.assertFalse(assignment.tasks.filter(bundle_code=bad_bundle).exists())

