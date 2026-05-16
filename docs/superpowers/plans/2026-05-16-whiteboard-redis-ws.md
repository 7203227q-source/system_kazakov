# Whiteboard (Redis + WebSocket) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести синхронизацию доски с HTTP polling + запись событий в БД на WebSocket через Django Channels + Redis, оставив сохранение итогового snapshot в БД.

**Architecture:** Клиенты подключаются по WebSocket к `/ws/board/<session_id>/`. Сервер авторизует пользователя, проверяет доступ к сессии, ретранслирует пачки событий всем подписчикам группы доски и пишет события в Redis (с TTL) для реконнекта. Сохранение `snapshot_json` остаётся через существующий HTTP эндпоинт.

**Tech Stack:** Django, Django Channels, channels-redis, Redis, ASGI (uvicorn), nginx (WebSocket proxy), pytest.

---

## File Structure

**Create:**
- `/workspace/examprep/routing.py` — websocket URL routing.
- `/workspace/core/consumers.py` — `WhiteboardConsumer` (access control + protocol + Redis storage).

**Modify:**
- `/workspace/examprep/asgi.py` — подключить Channels router и auth middleware.
- `/workspace/examprep/settings.py` — добавить `channels`, `ASGI_APPLICATION`, `CHANNEL_LAYERS`, `REDIS_URL`.
- `/workspace/core/templates/core/board.html` — заменить pull/flush на WebSocket.
- `/workspace/requirements.txt` — добавить Channels/Redis/ASGI зависимости.

**Test:**
- `/workspace/core/tests/test_whiteboard_ws.py` — тест доступа и доставки событий через WS.

---

### Task 1: Добавить зависимости (Channels + Redis backend + ASGI сервер)

**Files:**
- Modify: `/workspace/requirements.txt`

- [ ] **Step 1: Обновить зависимости**

В конец `requirements.txt` добавить:

```txt
channels>=4.0
channels-redis>=4.2
uvicorn>=0.30
redis>=5.0
```

- [ ] **Step 2: Проверить, что зависимости ставятся**

Run:

```bash
pip install -r requirements.txt
```

Expected: PASS (без ошибок компиляции wheels).

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add channels and redis deps for whiteboard ws"
```

---

### Task 2: Настроить Django для ASGI + Channels + Redis

**Files:**
- Modify: `/workspace/examprep/settings.py`
- Modify: `/workspace/examprep/asgi.py`
- Create: `/workspace/examprep/routing.py`

- [ ] **Step 1: Добавить Channels в INSTALLED_APPS**

В `examprep/settings.py`:

```py
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "channels",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.vk",
    "core",
]
```

- [ ] **Step 2: Добавить ASGI_APPLICATION и CHANNEL_LAYERS**

В `examprep/settings.py` после `WSGI_APPLICATION` добавить:

```py
ASGI_APPLICATION = "examprep.asgi.application"

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}
```

- [ ] **Step 3: Создать routing.py**

Создать `examprep/routing.py`:

```py
from django.urls import re_path
from core.consumers import WhiteboardConsumer

websocket_urlpatterns = [
    re_path(r"^ws/board/(?P<session_id>\\d+)/$", WhiteboardConsumer.as_asgi()),
]
```

- [ ] **Step 4: Подключить routing в asgi.py**

Обновить `examprep/asgi.py` до:

```py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

from examprep.routing import websocket_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "examprep.settings")

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
```

- [ ] **Step 5: Проверить импорт**

Run:

```bash
python -m compileall -q /workspace/examprep
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add examprep/settings.py examprep/asgi.py examprep/routing.py
git commit -m "feat: enable channels and redis channel layer"
```

---

### Task 3: Реализовать WhiteboardConsumer (WS протокол + Redis TTL events)

**Files:**
- Create: `/workspace/core/consumers.py`
- Modify: `/workspace/examprep/settings.py` (если нужно добавить параметры лимитов/TTL)

- [ ] **Step 1: Создать consumer с проверкой доступа**

Создать `core/consumers.py`:

```py
import json
import os

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import PermissionDenied
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

        session = await WhiteboardSession.objects.select_related("student", "tutor").aget(id=self.session_id)
        self.session = session

        if not await self._can_access(user, session):
            await self.close(code=4403)
            return

        self.group_name = f"whiteboard_{self.session_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

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
        events_out = []
        for item in items:
            kind = (item.get("kind") or "")[:40]
            payload = item.get("payload") or {}
            server_id = await self._next_server_id()
            events_out.append(
                {
                    "server_id": server_id,
                    "kind": kind,
                    "payload": payload,
                    "author_id": user.id,
                }
            )

        await self._redis_append_events(events_out)
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "whiteboard.events",
                "events": events_out,
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

    async def _can_access(self, user, session: WhiteboardSession) -> bool:
        role = getattr(user, "role", None)
        if role == "student":
            return session.student_id == user.id
        if role == "tutor":
            return session.tutor_id == user.id
        if role == "admin":
            return True
        return False

    async def _get_redis(self):
        import redis.asyncio as redis

        url = getattr(settings, "REDIS_URL", None) or os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
        return redis.from_url(url, decode_responses=True)

    async def _next_server_id(self) -> int:
        r = await self._get_redis()
        return int(await r.incr(_redis_key_seq(self.session_id)))

    async def _redis_append_events(self, events_out):
        r = await self._get_redis()
        key = _redis_key_events(self.session_id)
        ttl = int(os.environ.get("WHITEBOARD_REDIS_TTL_SECONDS", "21600"))
        limit = int(os.environ.get("WHITEBOARD_REDIS_EVENT_LIMIT", "10000"))

        pipe = r.pipeline()
        for e in events_out:
            pipe.rpush(key, json.dumps(e, ensure_ascii=False))
        pipe.ltrim(key, max(0, -limit), -1)
        pipe.expire(key, ttl)
        await pipe.execute()

    async def _redis_get_events_after(self, after_server_id: int):
        r = await self._get_redis()
        key = _redis_key_events(self.session_id)
        raw = await r.lrange(key, 0, -1)
        if not raw:
            return ([], True if after_server_id > 0 else False)

        events = []
        for s in raw:
            try:
                e = json.loads(s)
            except Exception:
                continue
            sid = e.get("server_id") or 0
            if isinstance(sid, int) and sid > after_server_id:
                events.append(e)
        return (events[:2000], False)
```

- [ ] **Step 2: Уточнить, что aget доступен**

Если версия Django/ORM не поддерживает `.aget()`, заменить на `database_sync_to_async(get_object_or_404(...))`. Проверить при запуске тестов.

- [ ] **Step 3: Smoke-check импорта**

Run:

```bash
python -m compileall -q /workspace/core
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add core/consumers.py
git commit -m "feat: add whiteboard websocket consumer"
```

---

### Task 4: Перевести board.html на WebSocket

**Files:**
- Modify: `/workspace/core/templates/core/board.html`

- [ ] **Step 1: Добавить состояние lastServerId и WS подключение**

В JS:
- заменить `lastEventId` на `lastServerId`
- добавить `let ws = null; let wsOpen = false;`
- добавить `function wsUrl()` чтобы выбирать `ws://` или `wss://`

```js
let lastServerId = 0;
let ws = null;
let wsOpen = false;

function wsUrl() {
  const proto = (window.location.protocol === 'https:') ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/board/${sessionId}/`;
}

function connectWs() {
  ws = new WebSocket(wsUrl());
  ws.addEventListener('open', () => {
    wsOpen = true;
    ws.send(JSON.stringify({ type: 'sync', after_server_id: lastServerId }));
  });
  ws.addEventListener('close', () => {
    wsOpen = false;
    setTimeout(connectWs, 500);
  });
  ws.addEventListener('message', (evt) => {
    let msg = null;
    try { msg = JSON.parse(evt.data); } catch (e) { return; }
    if (msg.type === 'events') {
      for (const e of (msg.events || [])) {
        lastServerId = Math.max(lastServerId, e.server_id || 0);
        try { applyEvent(e.kind, e.payload || {}); } catch (err) {}
      }
      return;
    }
    if (msg.type === 'sync_result') {
      if (msg.need_snapshot) {
        if (initialSnapshot) {
          try { state = JSON.parse(initialSnapshot); } catch (e) {}
          render();
        }
      }
      for (const e of (msg.events || [])) {
        lastServerId = Math.max(lastServerId, e.server_id || 0);
        try { applyEvent(e.kind, e.payload || {}); } catch (err) {}
      }
      return;
    }
  });
}
```

- [ ] **Step 2: Заменить flushLoop на WS-отправку батчами**

Заменить `flushLoop()`:

```js
async function flushLoop() {
  if (!wsOpen || !pending.length) return;
  const batch = pending.splice(0, 100);
  try {
    ws.send(JSON.stringify({ type: 'event_batch', events: batch }));
  } catch (e) {
    pending.unshift(...batch);
  }
}
```

- [ ] **Step 3: Убрать pullLoop и запускать connectWs**

Удалить `pullLoop` и его таймер. Запуск:

```js
connectWs();
setInterval(flushLoop, 50);
```

- [ ] **Step 4: Run compile (templates не компилируются)**

Сделать минимальный sanity:

```bash
python -m compileall -q /workspace/core
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/templates/core/board.html
git commit -m "feat: switch whiteboard sync from http polling to websocket"
```

---

### Task 5: Написать тесты WebSocket (доступ + доставка событий)

**Files:**
- Create: `/workspace/core/tests/test_whiteboard_ws.py`

- [ ] **Step 1: Добавить зависимости тест-раннера Channels**

Проверить, что `pytest` уже используется в репозитории (есть `core/tests/*`). Для channels тестов нужен `channels.testing.WebsocketCommunicator`.

- [ ] **Step 2: Написать тест доступа (forbidden)**

Создать `core/tests/test_whiteboard_ws.py`:

```py
import pytest
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model

from examprep.asgi import application
from core.models import WhiteboardSession, Assignment, Task, TaskType, ExamFormat, Subject


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_whiteboard_ws_forbidden_for_other_student():
    User = get_user_model()
    s1 = User.objects.create_user(username="s1", password="x", role="student")
    s2 = User.objects.create_user(username="s2", password="x", role="student")
    t = User.objects.create_user(username="t", password="x", role="tutor")

    subj = Subject.objects.create(name="Math")
    ef = ExamFormat.objects.create(subject=subj, name="Test", year=2026, is_active=True)
    tt = TaskType.objects.create(exam_format=ef, name="T1", number=1)
    task = Task.objects.create(task_type=tt, content_classic="x", solution_classic="y")
    a = Assignment.objects.create(student=s1, tutor=t, title="A", is_draft=False, is_deleted=False)
    session = WhiteboardSession.objects.create(student=s1, tutor=t, assignment=a, task=task)

    communicator = WebsocketCommunicator(application, f"/ws/board/{session.id}/")
    communicator.scope["user"] = s2
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()
```

- [ ] **Step 3: Написать тест доставки событий между двумя клиентами**

```py
@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_whiteboard_ws_broadcasts_events_between_participants():
    User = get_user_model()
    s = User.objects.create_user(username="s", password="x", role="student")
    t = User.objects.create_user(username="t2", password="x", role="tutor")

    subj = Subject.objects.create(name="Math2")
    ef = ExamFormat.objects.create(subject=subj, name="Test2", year=2026, is_active=True)
    tt = TaskType.objects.create(exam_format=ef, name="T1", number=1)
    task = Task.objects.create(task_type=tt, content_classic="x", solution_classic="y")
    a = Assignment.objects.create(student=s, tutor=t, title="A", is_draft=False, is_deleted=False)
    session = WhiteboardSession.objects.create(student=s, tutor=t, assignment=a, task=task)

    c1 = WebsocketCommunicator(application, f"/ws/board/{session.id}/")
    c1.scope["user"] = s
    ok1, _ = await c1.connect()
    assert ok1 is True

    c2 = WebsocketCommunicator(application, f"/ws/board/{session.id}/")
    c2.scope["user"] = t
    ok2, _ = await c2.connect()
    assert ok2 is True

    await c1.send_json_to({"type": "event_batch", "events": [{"kind": "set_object", "payload": {"object": {"id": "o1", "type": "line", "x1": 1, "y1": 2, "x2": 3, "y2": 4, "stroke": "#000", "width": 2}}}]})
    msg = await c2.receive_json_from(timeout=2)
    assert msg["type"] == "events"
    assert msg["events"][0]["kind"] == "set_object"
    assert msg["events"][0]["payload"]["object"]["id"] == "o1"

    await c1.disconnect()
    await c2.disconnect()
```

- [ ] **Step 4: Запустить тест**

Run:

```bash
pytest -q /workspace/core/tests/test_whiteboard_ws.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/tests/test_whiteboard_ws.py
git commit -m "test: add websocket tests for whiteboard"
```

---

### Task 6: Обновить деплой на VPS (systemd + nginx + redis)

**Files (repo):**
- Create: `/workspace/docs/superpowers/plans/2026-05-16-whiteboard-redis-ws-deploy.md`

- [ ] **Step 1: Redis на сервере**

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y redis-server
sudo systemctl enable --now redis-server
```

Проверка:

```bash
redis-cli ping
```

Expected: `PONG`.

- [ ] **Step 2: systemd unit для ASGI**

Пример `/etc/systemd/system/examprep.service` (адаптировать пути):

```ini
[Unit]
Description=examprep (ASGI)
After=network.target redis-server.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/examprep
Environment="DJANGO_SETTINGS_MODULE=examprep.settings"
Environment="REDIS_URL=redis://127.0.0.1:6379/0"
ExecStart=/var/www/examprep/venv/bin/uvicorn examprep.asgi:application --host 127.0.0.1 --port 8001
Restart=always

[Install]
WantedBy=multi-user.target
```

Команды:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now examprep
sudo systemctl status examprep --no-pager
```

- [ ] **Step 3: nginx config для WebSocket**

Фрагмент nginx (в server block):

```nginx
location /ws/ {
  proxy_pass http://127.0.0.1:8001;
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  proxy_set_header Host $host;
  proxy_read_timeout 60s;
}

location / {
  proxy_pass http://127.0.0.1:8001;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
}
```

Проверка:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

- [ ] **Step 4: Smoke check**

Открыть доску в браузере, убедиться что:
- Вкладка Network показывает WS соединение `/ws/board/<id>/` со статусом 101 Switching Protocols.
- Рисование у одного пользователя появляется у второго без задержек.

---

## Plan Self-Review

- Спека: `/workspace/docs/superpowers/specs/2026-05-16-whiteboard-redis-ws-design.md` покрыта задачами 1–6.
- Placeholder scan: отсутствуют “TODO/TBD”.
- Согласованность имен: `ws/board/<session_id>` одинаково в routing, consumer и клиенте.

*** End Patch}"}]}type":"commentary to=functions.apply_patch  大发快三是国家 EOF
