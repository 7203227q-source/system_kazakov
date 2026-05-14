from django.test import TestCase
from django.urls import reverse

from core.models import (
    Assignment,
    ExamFormat,
    StudentSubjectProfile,
    Subject,
    Task,
    TaskType,
    Topic,
    User,
)


class TutorDashboardShowsAllAssignmentsAcrossSubjectsTests(TestCase):
    def test_tutor_dashboard_does_not_hide_assignments_of_other_subjects(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subj1 = Subject.objects.create(name="Математика")
        subj2 = Subject.objects.create(name="Физика")
        StudentSubjectProfile.objects.create(student=student, subject=subj1, xp=0, level=1, target_score=80)
        StudentSubjectProfile.objects.create(student=student, subject=subj2, xp=0, level=1, target_score=80)

        ef1 = ExamFormat.objects.create(subject=subj1, name="ЕГЭ", year=2026, is_active=True)
        ef2 = ExamFormat.objects.create(subject=subj2, name="ЕГЭ физика", year=2026, is_active=True)

        topic1 = Topic.objects.create(subject=subj1, name="T1")
        topic2 = Topic.objects.create(subject=subj2, name="T2")
        tt1 = TaskType.objects.create(exam_format=ef1, number=1, name="1", max_points=1)
        tt2 = TaskType.objects.create(exam_format=ef2, number=1, name="1", max_points=1)
        task1 = Task.objects.create(topic=topic1, task_type=tt1, correct_answer="1", difficulty=10, exam_points=1)
        task2 = Task.objects.create(topic=topic2, task_type=tt2, correct_answer="1", difficulty=10, exam_points=1)

        a1 = Assignment.objects.create(tutor=tutor, student=student, title="Матем вариант", is_draft=False, exam_format=ef1)
        a2 = Assignment.objects.create(tutor=tutor, student=student, title="Физика вариант", is_draft=False, exam_format=ef2)
        a1.tasks.add(task1)
        a2.tasks.add(task2)

        self.client.login(username="t", password="pass")
        url = reverse("tutor_dashboard") + f"?student_id={student.id}&chart_subject_id={subj1.id}"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertIn("Матем вариант", html)
        # критично: физика тоже должна быть видна, даже если выбран график по математике
        self.assertIn("Физика вариант", html)

