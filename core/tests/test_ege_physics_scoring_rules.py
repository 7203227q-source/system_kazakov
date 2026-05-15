from django.test import TestCase

from core.models import Subject, ExamFormat, TaskType, Topic, Task
from core.scoring import score_short_answer


class EgePhysicsShortAnswerScoringRulesTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Физика")
        self.ef = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ физика", year=2026, is_active=True)
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

    def test_two_points_ordered_sequence_rules(self):
        # №6: 2 балла, порядок важен, 1 балл за одну ошибку в позиции
        task = self._task(6, 2, "1234")
        self.assertEqual(score_short_answer(task, "1234"), 2)
        self.assertEqual(score_short_answer(task, "1235"), 1)
        self.assertEqual(score_short_answer(task, "12 35"), 1)
        self.assertEqual(score_short_answer(task, "123"), 0)
        self.assertEqual(score_short_answer(task, "12345"), 0)

    def test_two_points_unordered_multiple_choice_rules(self):
        # №5: 2 балла, порядок не важен, 1 балл за один неверный/лишний/пропущенный символ
        task = self._task(5, 2, "13")
        self.assertEqual(score_short_answer(task, "31"), 2)
        self.assertEqual(score_short_answer(task, "3"), 1)      # один пропуск
        self.assertEqual(score_short_answer(task, "32"), 1)     # один неверный
        self.assertEqual(score_short_answer(task, "312"), 1)    # один лишний при остальных верных
        self.assertEqual(score_short_answer(task, "12"), 1)     # один неверный символ (и, как следствие, один не указан)

    def test_one_point_task20_order_irrelevant(self):
        task = self._task(20, 1, "12")
        self.assertEqual(score_short_answer(task, "21"), 1)
        self.assertEqual(score_short_answer(task, "2"), 0)
