from bs4 import BeautifulSoup
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class AssignmentFinishMissingPart2DoesNotLockTests(TestCase):
    def test_finish_with_missing_part2_preserves_drafts_and_keeps_input_editable(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")

        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ", year=2026, is_active=True)

        tt_test = TaskType.objects.create(exam_format=ef, number=1, name="Тест", max_points=1, is_extended_answer=False)
        tt_part2 = TaskType.objects.create(exam_format=ef, number=19, name="Часть 2", max_points=2, is_extended_answer=True)

        topic = Topic.objects.create(subject=subject, name="T")
        task_test = Task.objects.create(topic=topic, task_type=tt_test, correct_answer="2", difficulty=50, exam_points=1)
        task_part2 = Task.objects.create(topic=topic, task_type=tt_part2, correct_answer="", difficulty=50, exam_points=2)

        TaskVariant.objects.create(task=task_test, theme="classic", content="<p>U</p>", solution="<p>S</p>")
        TaskVariant.objects.create(task=task_part2, theme="classic", content="<p>U2</p>", solution="<p>S2</p>")

        assignment = Assignment.objects.create(tutor=tutor, student=student, title="A", is_draft=False)
        assignment.tasks.add(task_test, task_part2)

        self.client.login(username="s", password="pass")

        url = reverse("student_solve_assignment", args=[assignment.id])

        res = self.client.post(
            url,
            {
                "action": "finish",
                f"answer_{task_test.id}": "2",
            },
            follow=True,
        )

        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Не все задания 2-й части сданы")
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_completed)

        sub_test = Submission.objects.get(student=student, assignment=assignment, task=task_test)
        self.assertEqual(sub_test.user_answer, "2")
        self.assertIsNone(sub_test.is_correct)

        soup = BeautifulSoup(res.content, "html.parser")
        inp = soup.find("input", {"id": f"answer_{task_test.id}"})
        self.assertIsNotNone(inp)
        self.assertFalse(inp.has_attr("readonly"))

