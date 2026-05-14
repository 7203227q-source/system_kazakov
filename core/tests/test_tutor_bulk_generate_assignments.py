from datetime import date

from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, StudentSubjectProfile, Subject, Task, TaskType, TaskVariant, Topic, User


class TutorBulkGenerateAssignmentsTests(TestCase):
    def test_bulk_generate_creates_multiple_published_assignments_with_due_dates(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        StudentSubjectProfile.objects.create(student=student, subject=subj, exam_format=ef, xp=0, level=1, target_score=80)

        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1)
        topic = Topic.objects.create(subject=subj, name="T")
        for i in range(5):
            task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1, subtype_tag="A")
            TaskVariant.objects.create(task=task, theme="classic", content=f"<p>Q{i}</p>", solution="<p>S</p>")

        self.client.login(username="t", password="pass")
        url = reverse("tutor_create_assignment")
        res = self.client.post(url, data={
            "student_id": str(student.id),
            "exam_format": str(ef.id),
            "kind": "homework",
            "title": "",
            "generate_count": "2",
            "due_date": "2026-05-20",
            "due_step_days": "7",
            "submit_action": "publish_bulk",
            # выбор задач (минимально)
            f"type_count_{tt.id}": "1",
            "subtype_checked_1": "on",
            "subtype_name_1": "A",
            "subtype_type_1": str(tt.id),
            "subtype_count_1": "1",
        })
        # редирект на дашборд
        self.assertEqual(res.status_code, 302)

        qs = Assignment.objects.filter(tutor=tutor, student=student, exam_format=ef, is_draft=False)
        self.assertEqual(qs.count(), 2)
        dates = sorted([a.due_date for a in qs])
        self.assertEqual(dates, [date(2026, 5, 20), date(2026, 5, 27)])

