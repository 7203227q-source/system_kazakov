import asyncio
import json

from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from examprep.asgi import application

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User, TaskVariant, WhiteboardSession


class WhiteboardWebsocketTests(TransactionTestCase):
    async def _connect(self, user, session_id: int):
        communicator = WebsocketCommunicator(application, f"/ws/board/{session_id}/")
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        return communicator

    def test_tutor_event_broadcasts_to_student(self):
        tutor = User.objects.create_user(username="tutor1", password="x", role="tutor")
        student = User.objects.create_user(username="student1", password="x", role="student")
        tutor.students.add(student)

        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name="Тест", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="42", difficulty=50, exam_points=1)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Условие</p>", solution="<p>Решение</p>")

        assignment = Assignment.objects.create(tutor=tutor, student=student, title="Вариант 1", is_draft=False)
        assignment.tasks.add(task)
        session = WhiteboardSession.objects.create(
            student=student,
            tutor=tutor,
            assignment=assignment,
            task=task,
            snapshot_json='{"version":2,"objects":[]}',
        )

        async def run():
            c_tutor = await self._connect(tutor, session.id)
            c_student = await self._connect(student, session.id)

            msg = {"type": "stroke_start", "client_id": "t1", "seq": 1, "payload": {"id": "s1", "x": 1, "y": 2, "p": 0.5}}
            await c_tutor.send_to(text_data=json.dumps(msg))

            received = await c_student.receive_from(timeout=2)
            data = json.loads(received)
            self.assertEqual(data.get("type"), "stroke_start")
            self.assertEqual(data.get("payload", {}).get("id"), "s1")

            await c_tutor.disconnect()
            await c_student.disconnect()

        asyncio.run(run())

