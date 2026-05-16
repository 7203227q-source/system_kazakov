from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, Subject, Task, TaskLog, TaskType, TaskVariant, Topic, User


class StudentPracticeGapAnalysisNo500Tests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=self.subj, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1, is_extended_answer=False)
        topic = Topic.objects.create(subject=self.subj, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        SpacedRepetition.objects.create(student=self.student, task=self.task, next_review_date=timezone.now().date())

    def test_srs_submit_does_not_500_when_gap_analysis_has_both_verified_and_solo(self):
        TaskLog.objects.create(student=self.student, task=self.task, score=1.0, is_verified=False, is_anomaly=False)
        TaskLog.objects.create(student=self.student, task=self.task, score=0.5, is_verified=True, is_anomaly=False)

        self.client.force_login(self.student)
        r = self.client.get(reverse("student_practice") + "?mode=srs")
        self.assertEqual(r.status_code, 200)
        token = self.client.session.get("practice_current", {}).get("token")
        self.assertTrue(token)

        res = self.client.post(
            reverse("student_practice"),
            data={"task_id": self.task.id, "answer": "1", "mode": "srs", "attempt_token": token},
        )
        self.assertEqual(res.status_code, 200)

        self.student.refresh_from_db()
        prof = self.student.subject_profiles.filter(subject=self.subj).first()
        self.assertIsNotNone(prof)
        self.assertLessEqual(float(prof.trust_factor), 0.6)

    def test_srs_submit_does_not_500_with_corrupted_session_payload(self):
        self.client.force_login(self.student)
        r = self.client.get(reverse("student_practice") + "?mode=srs")
        self.assertEqual(r.status_code, 200)
        token = self.client.session.get("practice_current", {}).get("token")
        self.assertTrue(token)

        s = self.client.session
        s["practice_results"] = "oops"
        s["practice_current"] = "oops"
        s.save()

        res = self.client.post(
            reverse("student_practice"),
            data={"task_id": self.task.id, "answer": "1", "mode": "srs", "attempt_token": token},
        )
        self.assertEqual(res.status_code, 302)
