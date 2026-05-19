from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, StudentSubjectProfile, Subject, Task, TaskType, TaskVariant, Topic, User


class SrsCameraUploadAvailableTests(TestCase):
    def test_srs_extended_task_has_camera_inputs(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student.tutors.add(tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        StudentSubjectProfile.objects.create(student=student, subject=subj, exam_format=ef)
        tt = TaskType.objects.create(
            exam_format=ef,
            number=13,
            name="Развёрнутая",
            max_points=4,
            is_extended_answer=True,
        )
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="x", difficulty=10, exam_points=4)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>U</p>", solution="<p>S</p>")
        SpacedRepetition.objects.create(student=student, task=task, next_review_date=timezone.localdate())

        self.client.force_login(student)
        url = reverse("student_practice") + f"?mode=srs&subject_id={subj.id}"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")

        # Должна быть возможность открыть камеру (capture="environment") и выбрать файл из галереи.
        self.assertIn('capture="environment"', html)
        self.assertIn('id="srs_camera_1"', html)
        self.assertIn('id="srs_gallery_1"', html)
