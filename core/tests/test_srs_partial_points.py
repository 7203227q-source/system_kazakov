from django.test import TestCase

from core.models import ExamFormat, Subject, Task, TaskType, Topic
from core.scoring import score_short_answer_srs


class SRSPartialPointsTests(TestCase):
    def test_2_point_sequence_shorter_answer_gets_1_point_if_first_digit_matches(self):
        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ физика (тест)", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=12, name="Тест (2 балла)", max_points=2, is_extended_answer=False)
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="2413", exam_points=2)

        self.assertEqual(score_short_answer_srs(task, "2"), 1)

    def test_2_point_sequence_shorter_answer_gets_0_if_no_positions_match(self):
        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ физика (тест)", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=12, name="Тест (2 балла)", max_points=2, is_extended_answer=False)
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="2413", exam_points=2)

        self.assertEqual(score_short_answer_srs(task, "9"), 0)

    def test_2_point_sequence_exact_match_gets_2(self):
        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ физика (тест)", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=12, name="Тест (2 балла)", max_points=2, is_extended_answer=False)
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="2413", exam_points=2)

        self.assertEqual(score_short_answer_srs(task, "2413"), 2)

