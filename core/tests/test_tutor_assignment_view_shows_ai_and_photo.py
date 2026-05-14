from django.test import TestCase
from django.urls import reverse

from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, Topic, User


class TutorAssignmentViewShowsAiAndPhotoTests(TestCase):
    def test_page_renders_ai_block_when_feedback_present(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subj = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subj, name="T")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)
        a = Assignment.objects.create(tutor=tutor, student=student, title="A", is_draft=False, exam_format=ef)
        a.tasks.add(task)

        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xa6\x18\xdd\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        Submission.objects.create(student=student, task=task, assignment=a, image_url=image, ai_feedback="ok", primary_score=2)

        self.client.login(username="t", password="pass")
        r = self.client.get(reverse("tutor_assignment_view", args=[a.id]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertIn("Вердикт ИИ", html)
        self.assertIn("Оценено:", html)
        self.assertIn("Итог репетитора", html)

