from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, Topic, User


class TutorCreateAssignmentDynamicExamFormatTests(TestCase):
    def test_exam_formats_and_structure_depend_on_selected_student(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subj1 = Subject.objects.create(name="Математика")
        subj2 = Subject.objects.create(name="Физика")

        f1 = ExamFormat.objects.create(subject=subj1, name="ОГЭ математика", year=2026, is_active=True)
        f2 = ExamFormat.objects.create(subject=subj1, name="ЕГЭ математика", year=2026, is_active=True)
        f3 = ExamFormat.objects.create(subject=subj2, name="ЕГЭ физика", year=2026, is_active=True)

        student.subject_profiles.create(subject=subj1, target_score=80, level=1, xp=0, exam_format=f2)

        topic1 = Topic.objects.create(subject=subj1, name="Тема 1")
        topic2 = Topic.objects.create(subject=subj1, name="Тема 2")
        tt1 = TaskType.objects.create(exam_format=f1, number=1, name="Тип 1 ОГЭ", max_points=1)
        tt2 = TaskType.objects.create(exam_format=f2, number=99, name="Тип 99 ЕГЭ", max_points=2)
        Task.objects.create(topic=topic1, task_type=tt1, subtype_tag="a", correct_answer="1", difficulty=10, exam_points=1)
        Task.objects.create(topic=topic2, task_type=tt2, subtype_tag="b", correct_answer="1", difficulty=10, exam_points=1)

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_create_assignment"), {"student_id": str(student.id)})
        self.assertEqual(res.status_code, 200)

        self.assertContains(res, f1.name)
        self.assertContains(res, f2.name)
        self.assertNotContains(res, f3.name)

        self.assertContains(res, "№99. Тип 99 ЕГЭ")
        self.assertNotContains(res, "№1. Тип 1 ОГЭ")

        res2 = self.client.get(
            reverse("tutor_create_assignment"),
            {"student_id": str(student.id), "exam_format": str(f1.id)},
        )
        self.assertEqual(res2.status_code, 200)
        self.assertContains(res2, "№1. Тип 1 ОГЭ")
        self.assertNotContains(res2, "№99. Тип 99 ЕГЭ")

