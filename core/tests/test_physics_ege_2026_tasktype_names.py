from django.test import TestCase

from core.models import ExamFormat, Subject, TaskType


class PhysicsEGE2026TaskTypeNamesTests(TestCase):
    def test_physics_ege_2026_tasktype_names_are_descriptive(self):
        subj = Subject.objects.get(name="Физика")
        ef = ExamFormat.objects.get(subject=subj, name="ЕГЭ физика", year=2026)

        t1 = TaskType.objects.get(exam_format=ef, number=1)
        t5 = TaskType.objects.get(exam_format=ef, number=5)
        t21 = TaskType.objects.get(exam_format=ef, number=21)
        t26 = TaskType.objects.get(exam_format=ef, number=26)

        self.assertNotEqual(t1.name, "Задание №1")
        self.assertNotEqual(t5.name, "Задание №5")
        self.assertNotEqual(t21.name, "Задание №21")
        self.assertNotEqual(t26.name, "Задание №26")

        self.assertIn("Кинемат", t1.name)
        self.assertIn("Механ", t5.name)
        self.assertIn("Качествен", t21.name)
        self.assertIn("высок", t26.name.lower())

