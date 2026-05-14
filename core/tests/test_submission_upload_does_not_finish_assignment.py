import base64

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, Topic, User


class SubmissionUploadDoesNotFinishAssignmentTests(TestCase):
    def test_upload_photo_does_not_mark_assignment_completed(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        topic = Topic.objects.create(subject=subject, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)

        a = Assignment.objects.create(tutor=tutor, student=student, title="A", is_draft=False, is_completed=False, exam_format=ef)
        a.tasks.add(task)
        sub = Submission.objects.create(student=student, task=task, assignment=a)

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")

        self.client.force_login(student)
        url = reverse("api_submission_upload", args=[sub.id])
        res = self.client.post(url, data={"image": image})
        self.assertEqual(res.status_code, 200, res.content)

        a.refresh_from_db()
        self.assertFalse(a.is_completed)

