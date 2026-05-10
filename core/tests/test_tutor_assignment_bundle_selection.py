from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User


class TutorAssignmentBundleSelectionTests(TestCase):
    def test_selecting_type_1_pulls_full_bundle(self):
        tutor = User.objects.create_user(username="tutor", password="pass", role="tutor")
        student = User.objects.create_user(username="student", password="pass", role="student")
        tutor.students.add(student)
        self.client.login(username="tutor", password="pass")

        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания из Открытого Банка")

        task_types = {}
        for n in range(1, 6):
            task_types[n] = TaskType.objects.create(exam_format=exam_format, number=n, name=f"Тип {n}", max_points=1)

        bundle = "sdamgia_bundle:1-2-3-4-5"
        for n in range(1, 6):
            task = Task.objects.create(
                fipi_id=str(400000 + n),
                topic=topic,
                task_type=task_types[n],
                subtype_tag="block",
                bundle_code=bundle,
                correct_answer="1",
                difficulty=50,
                exam_points=1,
            )
            TaskVariant.objects.create(task=task, theme="classic", content="x", solution="y")

        t1 = task_types[1]
        post = {
            "student_id": str(student.id),
            f"type_count_{t1.id}": "1",
            "subtype_checked_1": "on",
            "subtype_name_1": "block",
            "subtype_type_1": str(t1.id),
        }
        res = self.client.post(reverse("tutor_create_assignment"), post)
        self.assertEqual(res.status_code, 302)

        from core.models import Assignment

        assignment = Assignment.objects.latest("id")
        self.assertEqual(assignment.tasks.count(), 5)

