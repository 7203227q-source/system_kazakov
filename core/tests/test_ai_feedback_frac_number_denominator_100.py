import base64

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class AIFeedbackFracNumberDenominator100Tests(TestCase):
    def test_frac40100_is_normalized_to_latex_frac(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student.tutors.add(tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=20, name="№20", max_points=2)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>SOLUTION</p>")

        assignment = Assignment.objects.create(tutor=tutor, student=student, title="A", is_draft=False)
        assignment.tasks.add(task)

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        sub = Submission.objects.create(student=student, assignment=assignment, task=task, image_url=image)
        sub.primary_score = 2
        sub.ai_feedback = "frac40100x + frac48100y = frac42100(x+y)"
        sub.save()

        self.client.login(username="s", password="pass")
        page = self.client.get(reverse("student_solve_assignment", args=[assignment.id]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "\\\\frac{40}{100}x + \\\\frac{48}{100}y = \\\\frac{42}{100}(x+y)")
