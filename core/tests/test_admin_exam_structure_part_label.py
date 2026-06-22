from django.test import TestCase
from django.urls import reverse

from core.models import Subject, ExamFormat, TaskType, User


class AdminExamStructurePartLabelTests(TestCase):
    def test_part_label_uses_is_extended_answer(self):
        admin = User.objects.create_user(username="admin_part_label", password="pw", role="admin")
        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ физика (тест)", year=2026, is_active=True)

        TaskType.objects.create(exam_format=ef, number=1, name="Тест", max_points=2, is_extended_answer=False)
        TaskType.objects.create(exam_format=ef, number=17, name="Развёрнутый", max_points=3, is_extended_answer=True)

        self.client.force_login(admin)
        res = self.client.get(reverse("admin_exam_structure"), {"exam_format": str(ef.id)})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Тестовая часть")
        self.assertContains(res, "Развёрнутая часть")
