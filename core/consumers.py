import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from core.models import WhiteboardSession


class WhiteboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return

        session_id_raw = self.scope.get("url_route", {}).get("kwargs", {}).get("session_id")
        try:
            self.session_id = int(session_id_raw)
        except Exception:
            await self.close(code=4400)
            return

        session = await self._get_session()
        if session is None:
            await self.close(code=4404)
            return

        if user.role == "student" and session.student_id != user.id:
            await self.close(code=4403)
            return
        if user.role == "tutor" and session.tutor_id != user.id:
            await self.close(code=4403)
            return
        if user.role not in {"student", "tutor", "admin"}:
            await self.close(code=4403)
            return

        self.group_name = f"whiteboard_{self.session_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        try:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        except Exception:
            pass

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except Exception:
            return

        msg_type = (data.get("type") or "")[:64]
        client_id = (data.get("client_id") or "")[:128]
        seq = 0
        try:
            seq = int(data.get("seq") or 0)
        except Exception:
            seq = 0
        payload = data.get("payload") or {}

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "board.event",
                "event": {"type": msg_type, "client_id": client_id, "seq": seq, "payload": payload},
            },
        )

    async def board_event(self, event):
        await self.send(text_data=json.dumps(event.get("event") or {}, ensure_ascii=False))

    @database_sync_to_async
    def _get_session(self):
        try:
            return WhiteboardSession.objects.only("id", "student_id", "tutor_id").get(id=self.session_id)
        except WhiteboardSession.DoesNotExist:
            return None

