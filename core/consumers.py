import json
import os

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from core.models import WhiteboardSession


def _redis_key_events(session_id: int) -> str:
    return f"wb:{session_id}:events"


def _redis_key_seq(session_id: int) -> str:
    return f"wb:{session_id}:seq"


class WhiteboardConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return

        session_id_raw = self.scope.get("url_route", {}).get("kwargs", {}).get("session_id")
        try:
            self.session_id = int(session_id_raw)
        except Exception:
            await self.close(code=4400)
            return

        session = await self._get_session(self.session_id)
        if session is None:
            await self.close(code=4404)
            return

        if not await self._can_access(user, session):
            await self.close(code=4403)
            return

        self.session = session
        self.group_name = f"whiteboard_{self.session_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type")
        if msg_type == "event_batch":
            await self._handle_event_batch(content)
            return
        if msg_type == "sync":
            await self._handle_sync(content)
            return

    async def whiteboard_events(self, event):
        await self.send_json({"type": "events", "events": event.get("events") or []})

    async def _handle_event_batch(self, content):
        user = self.scope["user"]
        items = content.get("events") or []
        if not isinstance(items, list) or not items:
            return

        items = items[:200]
        out = []
        for item in items:
            kind = (item.get("kind") or "")[:40]
            payload = item.get("payload") or {}
            server_id = await self._next_server_id()
            out.append(
                {
                    "server_id": server_id,
                    "kind": kind,
                    "payload": payload,
                    "author_id": user.id,
                }
            )

        await self._redis_append_events(out)
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "whiteboard.events",
                "events": out,
            },
        )

    async def _handle_sync(self, content):
        after_server_id = content.get("after_server_id") or 0
        try:
            after_server_id = int(after_server_id)
        except Exception:
            after_server_id = 0

        events, need_snapshot = await self._redis_get_events_after(after_server_id)
        await self.send_json({"type": "sync_result", "events": events, "need_snapshot": need_snapshot})

    async def _get_redis(self):
        import redis.asyncio as redis

        if os.environ.get("WHITEBOARD_DISABLE_REDIS") == "1":
            return None

        r = getattr(self, "_redis", None)
        if r is not None:
            return r
        url = getattr(settings, "REDIS_URL", None) or os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
        self._redis = redis.from_url(url, decode_responses=True)
        return self._redis

    async def _next_server_id(self) -> int:
        r = await self._get_redis()
        if r is None:
            current = getattr(self, "_fallback_server_id", 0)
            current += 1
            self._fallback_server_id = current
            return current
        try:
            return int(await r.incr(_redis_key_seq(self.session_id)))
        except Exception:
            current = getattr(self, "_fallback_server_id", 0)
            current += 1
            self._fallback_server_id = current
            return current

    async def _redis_append_events(self, events):
        r = await self._get_redis()
        if r is None:
            return
        key = _redis_key_events(self.session_id)
        ttl = int(os.environ.get("WHITEBOARD_REDIS_TTL_SECONDS", "21600"))
        limit = max(1, int(os.environ.get("WHITEBOARD_REDIS_EVENT_LIMIT", "10000")))

        try:
            pipe = r.pipeline()
            for e in events:
                pipe.rpush(key, json.dumps(e, ensure_ascii=False))
            pipe.ltrim(key, -limit, -1)
            pipe.expire(key, ttl)
            await pipe.execute()
        except Exception:
            return

    async def _redis_get_events_after(self, after_server_id: int):
        r = await self._get_redis()
        if r is None:
            return ([], False)
        key = _redis_key_events(self.session_id)
        try:
            raw = await r.lrange(key, 0, -1)
        except Exception:
            return ([], False)
        if not raw:
            return ([], bool(after_server_id))

        events = []
        for item in raw:
            try:
                e = json.loads(item)
            except Exception:
                continue
            sid = e.get("server_id") or 0
            if isinstance(sid, int) and sid > after_server_id:
                events.append(e)
        return (events[:2000], False)

    @database_sync_to_async
    def _get_session(self, session_id: int):
        return (
            WhiteboardSession.objects.select_related("student", "tutor", "assignment", "task")
            .filter(id=session_id)
            .first()
        )

    async def _can_access(self, user, session: WhiteboardSession) -> bool:
        role = getattr(user, "role", None)
        if role == "student":
            if session.student_id != user.id:
                return False
            if self._student_whiteboard_unlocked(session.assignment_id, session.task_id):
                return True
            current_id = self._student_whiteboard_current_session_id(session.assignment_id, session.task_id)
            return bool(current_id and current_id == session.id)
        if role == "tutor":
            return session.tutor_id == user.id
        if role == "admin":
            return True
        return False

    def _whiteboard_key(self, assignment_id: int, task_id: int):
        return f"{int(assignment_id)}:{int(task_id)}"

    def _student_whiteboard_unlocked(self, assignment_id: int, task_id: int):
        s = self.scope.get("session")
        unlocked = (s.get("whiteboard_unlocked", {}) if s else {}) or {}
        return bool(unlocked.get(self._whiteboard_key(assignment_id, task_id)))

    def _student_whiteboard_current_session_id(self, assignment_id: int, task_id: int):
        s = self.scope.get("session")
        current = (s.get("whiteboard_current", {}) if s else {}) or {}
        sid = current.get(self._whiteboard_key(assignment_id, task_id))
        try:
            return int(sid) if sid is not None else None
        except Exception:
            return None
