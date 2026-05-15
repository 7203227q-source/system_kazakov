from django.test import TestCase

from core.models import User, Subject, Topic, Task, TaskVariant, Submission, SubmissionComment, StudentSubjectProfile, ExamFormat


class StudentDashboardCommentsPanelTests(TestCase):
    def test_student_dashboard_contains_recent_comments(self):
        student = User.objects.create_user(username="s1", password="pw", role="student")
        tutor = User.objects.create_user(username="t1", password="pw", role="tutor")
        student.tutors.add(tutor)

        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ЕГЭ физика", year=2026, is_active=True)
        StudentSubjectProfile.objects.create(student=student, subject=subject, exam_format=ef, xp=0, level=1, target_score=80)
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, correct_answer="1", exam_points=1)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        sub = Submission.objects.create(student=student, task=task, user_answer="1", is_correct=True, score=1)
        SubmissionComment.objects.create(submission=sub, author=tutor, author_role="tutor", text="Ответ репетитора")

        self.client.force_login(student)
        res = self.client.get("/student/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Комментарии")
        self.assertContains(res, "Ответ репетитора")
