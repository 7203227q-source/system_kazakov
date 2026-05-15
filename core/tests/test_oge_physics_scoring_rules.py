from django.test import TestCase

from core.models import Subject, ExamFormat, TaskType, Topic, Task
from core.scoring import score_short_answer


class OgePhysicsShortAnswerScoringRulesTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Физика")
        self.ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ физика", year=2026, is_active=True)
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")

    def _task(self, number: int, max_points: int, correct_answer: str):
        tt = TaskType.objects.create(
            exam_format=self.ef,
            number=number,
            name=f"№{number}",
            max_points=max_points,
            is_extended_answer=False,
        )
        return Task.objects.create(topic=self.topic, task_type=tt, correct_answer=correct_answer, exam_points=1)

    def test_ordered_sequence_2_points_rules(self):
        # №1: порядок важен
        task = self._task(1, 2, "12")
        self.assertEqual(score_short_answer(task, "12"), 2)
        self.assertEqual(score_short_answer(task, "13"), 1)  # одна ошибка в позиции
        self.assertEqual(score_short_answer(task, "1 3"), 1)  # нормализация ввода
        self.assertEqual(score_short_answer(task, "1"), 0)  # длина не совпала
        self.assertEqual(score_short_answer(task, "123"), 0)  # лишние символы

    def test_unordered_sequence_2_points_rules(self):
        # №14: порядок не важен
        task = self._task(14, 2, "13")
        self.assertEqual(score_short_answer(task, "31"), 2)
        self.assertEqual(score_short_answer(task, "32"), 1)  # один неверный символ
        self.assertEqual(score_short_answer(task, "3"), 1)  # один символ отсутствует
        self.assertEqual(score_short_answer(task, "123"), 0)  # лишний символ

