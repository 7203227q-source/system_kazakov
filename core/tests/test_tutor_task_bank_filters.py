from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, Topic, User


class TutorTaskBankFiltersTests(TestCase):
    def test_tutor_subjects_and_exam_formats_are_limited_to_their_students(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        s1 = User.objects.create_user(username="s1", password="pass", role="student")
        s2 = User.objects.create_user(username="s2", password="pass", role="student")
        tutor.students.add(s1)

        subj1 = Subject.objects.create(name="Математика")
        subj2 = Subject.objects.create(name="Физика")
        f1 = ExamFormat.objects.create(subject=subj1, name="ОГЭ математика", year=2026, is_active=True)
        f2 = ExamFormat.objects.create(subject=subj2, name="ЕГЭ физика", year=2026, is_active=True)

        topic1 = Topic.objects.create(subject=subj1, name="T1")
        topic2 = Topic.objects.create(subject=subj2, name="T2")
        tt1 = TaskType.objects.create(exam_format=f1, number=1, name="Тип 1", max_points=1)
        tt2 = TaskType.objects.create(exam_format=f2, number=1, name="Тип 1", max_points=1)
        Task.objects.create(topic=topic1, task_type=tt1, subtype_tag="a", correct_answer="1", difficulty=10, exam_points=1)
        Task.objects.create(topic=topic2, task_type=tt2, subtype_tag="b", correct_answer="1", difficulty=10, exam_points=1)

        s1.subject_profiles.create(subject=subj1, target_score=80, level=1, xp=0, exam_format=f1)
        s2.subject_profiles.create(subject=subj2, target_score=80, level=1, xp=0, exam_format=f2)

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_task_bank"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'name="subject"')
        self.assertContains(res, 'name="exam_format"')
        self.assertContains(res, subj1.name)
        self.assertNotContains(res, subj2.name)
