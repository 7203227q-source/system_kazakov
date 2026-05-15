from django.test import TestCase

from core.models import User, Subject, ExamFormat, TaskType, Topic, Task, TaskVariant, Assignment


class StudentAssignmentAiBlockPresentTests(TestCase):
    def test_ai_feedback_block_container_present_for_extended_task(self):
        tutor = User.objects.create_user(username="t1", password="pw", role="tutor")
        student = User.objects.create_user(username="s1", password="pw", role="student")
        tutor.students.add(student)

        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=25, name="Развёрнутая", max_points=3, is_extended_answer=True)
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="", exam_points=3)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        assignment = Assignment.objects.create(tutor=tutor, student=student, title="Вариант", is_draft=False, is_deleted=False)
        assignment.tasks.add(task)

        self.client.force_login(student)
        res = self.client.get(f"/student/assignment/{assignment.id}/")
        self.assertEqual(res.status_code, 200)

        html = res.content.decode("utf-8", errors="ignore")
        # контейнер должен присутствовать, даже если ai_feedback ещё нет
        self.assertIn(f"ai_feedback_block_{task.id}", html)

