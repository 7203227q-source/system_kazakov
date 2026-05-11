from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User, StudentSubjectProfile


class StudentExamFormatSwitchTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor.students.add(self.student)

        self.subject = Subject.objects.create(name="Математика")
        self.ef_oge = ExamFormat.objects.create(subject=self.subject, name="ОГЭ математика", year=2026, is_active=True)
        self.ef_ege = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ математика", year=2026, is_active=False)
        self.topic = Topic.objects.create(subject=self.subject, name="Задания")

        t_oge = TaskType.objects.create(exam_format=self.ef_oge, number=1, name="Тип 1", max_points=1)
        t_ege = TaskType.objects.create(exam_format=self.ef_ege, number=1, name="Тип 1", max_points=1)
        self.task_oge = Task.objects.create(topic=self.topic, task_type=t_oge, subtype_tag="x", correct_answer="1", difficulty=50, exam_points=1)
        self.task_ege = Task.objects.create(topic=self.topic, task_type=t_ege, subtype_tag="x", correct_answer="1", difficulty=50, exam_points=1)
        TaskVariant.objects.create(task=self.task_oge, theme="classic", content="x", solution="y")
        TaskVariant.objects.create(task=self.task_ege, theme="classic", content="x", solution="y")

        self.profile = StudentSubjectProfile.objects.create(student=self.student, subject=self.subject, target_score=80)

    def test_assignment_stores_selected_exam_format(self):
        self.client.login(username="t", password="pass")
        post = {
            "student_id": str(self.student.id),
            "exam_format": str(self.ef_ege.id),
            f"type_count_{self.task_ege.task_type_id}": "1",
            "subtype_checked_1": "on",
            "subtype_name_1": "x",
            "subtype_type_1": str(self.task_ege.task_type_id),
        }
        res = self.client.post(reverse("tutor_create_assignment"), post)
        self.assertEqual(res.status_code, 302)
        a = Assignment.objects.latest("id")
        self.assertEqual(a.exam_format_id, self.ef_ege.id)

    def test_student_can_switch_exam_format_on_profile(self):
        self.client.login(username="s", password="pass")
        res = self.client.post(reverse("student_update_exam_format"), {"subject_id": str(self.subject.id), "exam_format_id": str(self.ef_ege.id)})
        self.assertEqual(res.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.exam_format_id, self.ef_ege.id)

