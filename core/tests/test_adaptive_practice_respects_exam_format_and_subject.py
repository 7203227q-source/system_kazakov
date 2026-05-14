from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, StudentSubjectProfile, Subject, Task, TaskType, TaskVariant, Topic, User


class AdaptivePracticeRespectsExamFormatAndSubjectTests(TestCase):
    def test_adaptive_uses_selected_subject_and_profile_exam_format(self):
        student = User.objects.create_user(username="s", password="pass", role="student")

        subj_math = Subject.objects.create(name="Математика")
        subj_phys = Subject.objects.create(name="Физика")

        ef_math_1 = ExamFormat.objects.create(subject=subj_math, name="ЕГЭ", year=2026, is_active=True)
        ef_math_2 = ExamFormat.objects.create(subject=subj_math, name="ОГЭ", year=2026, is_active=False)
        ef_phys = ExamFormat.objects.create(subject=subj_phys, name="ЕГЭ физика", year=2026, is_active=True)

        # У ученика выбран ЕГЭ по математике и ЕГЭ по физике
        StudentSubjectProfile.objects.create(student=student, subject=subj_math, exam_format=ef_math_1, xp=0, level=1, target_score=80)
        StudentSubjectProfile.objects.create(student=student, subject=subj_phys, exam_format=ef_phys, xp=0, level=1, target_score=80)

        # Математика: две задачи, но в разных форматах
        topic_math = Topic.objects.create(subject=subj_math, name="Tmath")
        tt_math_1 = TaskType.objects.create(exam_format=ef_math_1, number=1, name="1", max_points=1)
        tt_math_2 = TaskType.objects.create(exam_format=ef_math_2, number=1, name="1", max_points=1)
        task_math_ok = Task.objects.create(topic=topic_math, task_type=tt_math_1, correct_answer="1", difficulty=10, exam_points=1)
        task_math_bad = Task.objects.create(topic=topic_math, task_type=tt_math_2, correct_answer="1", difficulty=10, exam_points=1)
        TaskVariant.objects.create(task=task_math_ok, theme="classic", content="<p>Q1</p>", solution="<p>S</p>")
        TaskVariant.objects.create(task=task_math_bad, theme="classic", content="<p>Q2</p>", solution="<p>S</p>")

        # Физика: задача
        topic_phys = Topic.objects.create(subject=subj_phys, name="Tphys")
        tt_phys = TaskType.objects.create(exam_format=ef_phys, number=1, name="1", max_points=1)
        task_phys = Task.objects.create(topic=topic_phys, task_type=tt_phys, correct_answer="1", difficulty=10, exam_points=1)
        TaskVariant.objects.create(task=task_phys, theme="classic", content="<p>Q3</p>", solution="<p>S</p>")

        self.client.force_login(student)

        # Выбираем математику: должен прийти task_math_ok (ЕГЭ), а не task_math_bad (ОГЭ) и не физика
        r = self.client.get(reverse("student_practice") + f"?subject_id={subj_math.id}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Q1", r.content.decode("utf-8"))
        self.assertNotIn("Q2", r.content.decode("utf-8"))
        self.assertNotIn("Q3", r.content.decode("utf-8"))

