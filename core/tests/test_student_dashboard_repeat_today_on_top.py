from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Assignment, ExamFormat, SpacedRepetition, StudentSubjectProfile, Subject, Task, TaskType, Topic, User


class StudentDashboardRepeatTodayOnTopTests(TestCase):
    def test_repeat_today_block_is_above_assignments_list(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        student.tutors.add(tutor)

        subj = Subject.objects.create(name="Математика")
        StudentSubjectProfile.objects.create(student=student, subject=subj, xp=0, level=1, target_score=80)
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        a = Assignment.objects.create(tutor=tutor, student=student, title="Вариант 1", is_draft=False, is_completed=False, exam_format=ef)
        a.tasks.add(task)

        SpacedRepetition.objects.create(student=student, task=task, next_review_date=timezone.now().date())

        self.client.login(username="s", password="pass")
        r = self.client.get(reverse("student_dashboard"))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")

        idx_repeat = html.find("Повторить сегодня")
        idx_assignment = html.find("Вариант 1")
        idx_practice = html.find("Тренажер: Случайные задания")
        self.assertTrue(idx_repeat != -1 and idx_assignment != -1 and idx_practice != -1)
        self.assertLess(idx_repeat, idx_assignment)
        self.assertLess(idx_repeat, idx_practice)

