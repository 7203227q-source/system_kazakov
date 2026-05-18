import base64
import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class StudentSolveAssignmentPhotoUiTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="tutor", password="pw", role="tutor")
        self.student = User.objects.create_user(username="student", password="pw", role="student")

        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")

        self.task_type = TaskType.objects.create(
            exam_format=self.exam_format,
            number=20,
            name="Тип 20",
            max_points=2,
            is_extended_answer=True,
        )
        self.task = Task.objects.create(
            topic=self.topic,
            task_type=self.task_type,
            correct_answer="1",
            difficulty=10,
            exam_points=2,
        )
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        self.assignment = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="A",
            is_draft=False,
            is_completed=False,
            is_deleted=False,
            exam_format=self.exam_format,
        )
        self.assignment.tasks.add(self.task)

    def test_after_first_page_upload_js_does_not_use_block_innerhtml(self):
        """
        Регрессия: раньше после загрузки 1-й страницы JS подменял HTML (block.innerHTML),
        из-за чего пропадали кнопки "Удалить фото" и "Добавить 2-ю страницу".
        Теперь после успешной загрузки должен быть reload страницы.
        """
        self.client.force_login(self.student)
        html = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id])).content.decode("utf-8")

        assert "block.innerHTML" not in html
        assert "location.reload()" in html

    def test_student_solve_assignment_has_second_page_camera_input(self):
        self.client.force_login(self.student)

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")

        # создаём submission с 1-й страницей, чтобы отрисовалась ветка "Фото уже загружено"
        Submission.objects.create(student=self.student, task=self.task, assignment=self.assignment, image_url=image)

        html = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id])).content.decode("utf-8")
        assert re.search(r'id="camera_file2_\d+".*capture="environment"', html)
