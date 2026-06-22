from django.test import TestCase

from core.models import ExamFormat, Subject, TaskType


class TaskTypeExplanationEffectiveTests(TestCase):
    def test_english_subject_prefers_explanation_en(self):
        subj = Subject.objects.create(name="Английский язык")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ английский", year=2026, is_active=True)
        tt = TaskType.objects.create(
            exam_format=ef,
            number=1,
            name="Тип 1",
            max_points=1,
            explanation="RU",
            explanation_en="EN",
        )
        self.assertEqual(tt.explanation_effective, "EN")

    def test_non_english_subject_uses_explanation(self):
        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ математика", year=2026, is_active=True)
        tt = TaskType.objects.create(
            exam_format=ef,
            number=1,
            name="Тип 1",
            max_points=1,
            explanation="RU",
            explanation_en="EN",
        )
        self.assertEqual(tt.explanation_effective, "RU")

    def test_english_subject_falls_back_to_ru_when_en_empty(self):
        subj = Subject.objects.create(name="Английский язык")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ английский", year=2026, is_active=True)
        tt = TaskType.objects.create(
            exam_format=ef,
            number=1,
            name="Тип 1",
            max_points=1,
            explanation="RU",
            explanation_en="",
        )
        self.assertEqual(tt.explanation_effective, "RU")

