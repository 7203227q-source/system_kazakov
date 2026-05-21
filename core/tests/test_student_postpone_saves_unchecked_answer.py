import re

from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class StudentPostponeSavesUncheckedAnswerTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)
        self.student.draft_check_probability = 0
        self.student.save(update_fields=["draft_check_probability"])

        subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1, is_extended_answer=False)
        topic = Topic.objects.create(subject=subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="2", difficulty=10, exam_points=1)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>U</p>", solution="<p>S</p>")

        self.assignment = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="A",
            is_draft=False,
            exam_format=ef,
        )
        self.assignment.tasks.add(self.task)

    def test_postpone_saves_answer_as_unchecked_and_allows_later_check(self):
        self.client.login(username="s", password="pass")
        url = reverse("student_solve_assignment", args=[self.assignment.id])

        res = self.client.post(url, data={f"answer_{self.task.id}": "1", "action": "postpone"})
        self.assertEqual(res.status_code, 302)

        sub = Submission.objects.get(student=self.student, assignment=self.assignment, task=self.task)
        self.assertEqual(sub.user_answer, "1")
        self.assertIsNone(sub.is_correct)
        self.assertEqual(int(sub.score or 0), 0)

        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        html = page.content.decode("utf-8")
        self.assertNotIn(f'upload_block_{self.task.id}', html)

        input_tag = re.search(rf'<input[^>]+id="answer_{self.task.id}"[^>]*>', html)
        self.assertIsNotNone(input_tag)
        self.assertNotIn("readonly", input_tag.group(0))

        btn_tag = re.search(
            r'(<button[^>]*class="[^"]*check-btn[^"]*"[^>]*>)[\s\S]*?<i class="fas fa-check mr-2"></i>\s*Проверить',
            html,
        )
        anchor = f'id="answer_{self.task.id}"'
        pos = html.find(anchor)
        debug = html[max(0, pos - 300): pos + 700] if pos != -1 else html[:2000]
        self.assertIsNotNone(btn_tag, debug)
        self.assertNotIn("disabled", btn_tag.group(1))

        check_url = reverse("student_check_assignment_task", args=[self.assignment.id, self.task.id])
        res2 = self.client.post(check_url, {"answer": "1"})
        self.assertEqual(res2.status_code, 200)
        self.assertFalse(res2.json()["is_correct"])
        self.assertTrue(res2.json().get("locked"))

        sub.refresh_from_db()
        self.assertEqual(sub.user_answer, "1")
        self.assertFalse(sub.is_correct)
