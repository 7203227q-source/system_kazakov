from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, StudentSubjectProfile, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class TutorDashboardSubjectSwitcherTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor.students.add(self.student)

        self.subj_math = Subject.objects.create(name="Математика")
        self.subj_phys = Subject.objects.create(name="Физика")
        self.ef_math = ExamFormat.objects.create(subject=self.subj_math, name="ЕГЭ", year=2026, is_active=True)
        self.ef_phys = ExamFormat.objects.create(subject=self.subj_phys, name="ЕГЭ", year=2026, is_active=True)
        StudentSubjectProfile.objects.create(student=self.student, subject=self.subj_math, exam_format=self.ef_math)
        StudentSubjectProfile.objects.create(student=self.student, subject=self.subj_phys, exam_format=self.ef_phys)
        self.tt_math = TaskType.objects.create(exam_format=self.ef_math, number=1, name="M1", max_points=1, is_extended_answer=False)
        self.tt_phys = TaskType.objects.create(exam_format=self.ef_phys, number=1, name="P1", max_points=1, is_extended_answer=False)
        self.topic_math = Topic.objects.create(subject=self.subj_math, name="TM")
        self.topic_phys = Topic.objects.create(subject=self.subj_phys, name="TP")
        self.task_math = Task.objects.create(topic=self.topic_math, task_type=self.tt_math, correct_answer="1", difficulty=10, exam_points=1)
        self.task_phys = Task.objects.create(topic=self.topic_phys, task_type=self.tt_phys, correct_answer="1", difficulty=10, exam_points=1)
        TaskVariant.objects.create(task=self.task_math, theme="classic", content="<p>Q</p>", solution="")
        TaskVariant.objects.create(task=self.task_phys, theme="classic", content="<p>Q</p>", solution="")

        a_math = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A1", is_draft=False, is_completed=False, exam_format=self.ef_math)
        a_math.tasks.add(self.task_math)
        a_phys = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A2", is_draft=False, is_completed=False, exam_format=self.ef_phys)
        a_phys.tasks.add(self.task_phys)

        Submission.objects.create(student=self.student, task=self.task_math, assignment=a_math, user_answer="1", is_correct=True, score=1)
        Submission.objects.create(student=self.student, task=self.task_phys, assignment=a_phys, user_answer="0", is_correct=False, score=0)

    def test_totals_and_accuracy_switch_with_subject(self):
        self.client.login(username="t", password="pass")

        url_math = f"{reverse('tutor_dashboard')}?student_id={self.student.id}&subject_id={self.subj_math.id}"
        page_math = self.client.get(url_math)
        self.assertEqual(page_math.status_code, 200)
        self.assertContains(page_math, "Попыток:")
        self.assertContains(page_math, ">1<")
        self.assertContains(page_math, "100")

        url_phys = f"{reverse('tutor_dashboard')}?student_id={self.student.id}&subject_id={self.subj_phys.id}"
        page_phys = self.client.get(url_phys)
        self.assertEqual(page_phys.status_code, 200)
        self.assertContains(page_phys, "Попыток:")
        self.assertContains(page_phys, ">1<")
        self.assertContains(page_phys, "0")
