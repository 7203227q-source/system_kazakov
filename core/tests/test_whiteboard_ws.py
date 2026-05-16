import os

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import TestCase
from django.test.utils import override_settings

from examprep.asgi import application
from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User, TaskVariant, WhiteboardSession


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class WhiteboardWebsocketTests(TestCase):
    def setUp(self):
        os.environ["WHITEBOARD_DISABLE_REDIS"] = "1"
        self.tutor = User.objects.create_user(username='tutor1', password='x', role='tutor')
        self.student = User.objects.create_user(username='student1', password='x', role='student')
        self.other_student = User.objects.create_user(username='student2', password='x', role='student')
        self.admin = User.objects.create_user(username='admin1', password='x', role='admin')

        subject = Subject.objects.create(name='Математика')
        exam_format = ExamFormat.objects.create(subject=subject, name='ЕГЭ', year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name='Тест', max_points=1)
        topic = Topic.objects.create(subject=subject, name='Тема')
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer='42', difficulty=50, exam_points=1)
        TaskVariant.objects.create(task=self.task, theme='classic', content='<p>Условие</p>', solution='<p>Решение</p>')

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title='Вариант 1', is_draft=False)
        self.assignment.tasks.add(self.task)

        self.board_session = WhiteboardSession.objects.create(student=self.student, tutor=self.tutor, assignment=self.assignment, task=self.task)

    def tearDown(self):
        os.environ.pop("WHITEBOARD_DISABLE_REDIS", None)
        super().tearDown()

    def test_other_student_cannot_connect(self):
        async def run():
            communicator = WebsocketCommunicator(application, f"/ws/board/{self.board_session.id}/")
            communicator.scope["user"] = self.other_student
            connected, _ = await communicator.connect()
            if connected:
                await communicator.disconnect()
            return connected

        connected = async_to_sync(run)()
        self.assertFalse(connected)

    def test_broadcasts_events_between_student_and_tutor(self):
        async def run():
            c1 = WebsocketCommunicator(application, f"/ws/board/{self.board_session.id}/")
            c1.scope["user"] = self.tutor
            ok1, _ = await c1.connect()

            c2 = WebsocketCommunicator(application, f"/ws/board/{self.board_session.id}/")
            c2.scope["user"] = self.admin
            ok2, _ = await c2.connect()

            try:
                if not ok1 or not ok2:
                    return (ok1, ok2, None)

                await c1.send_json_to(
                    {
                        "type": "event_batch",
                        "events": [
                            {
                                "kind": "set_object",
                                "payload": {
                                    "object": {
                                        "id": "o1",
                                        "type": "line",
                                        "x1": 1,
                                        "y1": 2,
                                        "x2": 3,
                                        "y2": 4,
                                        "stroke": "#000",
                                        "width": 2,
                                    }
                                },
                            }
                        ],
                    }
                )

                msg = await c2.receive_json_from(timeout=2)
                return (ok1, ok2, msg)
            finally:
                if ok1:
                    await c1.disconnect()
                if ok2:
                    await c2.disconnect()

        ok1, ok2, msg = async_to_sync(run)()
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertEqual(msg.get("type"), "events")
        self.assertEqual(msg["events"][0]["kind"], "set_object")
        self.assertEqual(msg["events"][0]["payload"]["object"]["id"], "o1")
