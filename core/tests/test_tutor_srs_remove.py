from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, Subject, Task, TaskType, Topic, User


class TutorSrsRemoveTests(TestCase):
    def test_tutor_can_remove_student_srs_item(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subject = Subject.objects.create(name="Математика")
        fmt = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subject, name="T")
        tt = TaskType.objects.create(exam_format=fmt, number=1, name="Тип 1", max_points=1)
        task = Task.objects.create(topic=topic, task_type=tt, subtype_tag="x", correct_answer="1", difficulty=10, exam_points=1)

        SpacedRepetition.objects.create(student=student, task=task, next_review_date=timezone.now().date())

        self.client.login(username="t", password="pass")
        res = self.client.post(reverse("tutor_student_srs_remove", args=[student.id, task.id]))
        self.assertEqual(res.status_code, 302)
        self.assertFalse(SpacedRepetition.objects.filter(student=student, task=task).exists())

