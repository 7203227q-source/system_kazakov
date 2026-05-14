# Whiteboard V2 (Konva + Channels + Redis) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Полностью заменить доску V1 (SVG+polling) на новую доску V2 на Konva.js с realtime через WebSocket (Django Channels + Redis), поддержкой pressure, карточкой условия на холсте и проверкой доски ИИ (баллы+комментарий).

**Architecture:** HTTP остаётся для страницы/создания/списка/сохранения snapshot, realtime-события идут через WebSocket consumer в Channels группе `whiteboard_<session_id>`. Состояние хранится как snapshot JSON в `WhiteboardSession.snapshot_json`. ИИ-вердикт сохраняется в полях `WhiteboardSession` и возвращается на клиент.

**Tech Stack:** Django 6, Channels, channels-redis, Redis, Konva.js (CDN), vanilla JS.

---

## Файлы и ответственность

**Modify:**
- `requirements.txt` — добавить зависимости Channels/Redis/ASGI server.
- `examprep/settings.py` — `channels`, `ASGI_APPLICATION`, `CHANNEL_LAYERS`.
- `examprep/asgi.py` — `ProtocolTypeRouter` + websocket routing.
- `examprep/urls.py` — добавить websocket URL? (WS routing будет в отдельном routing module; HTTP urls остаются в `core/urls.py`).
- `core/urls.py` — удалить polling endpoints `events/pull`, `events/append`, добавить `verify-ai`.
- `core/views.py` — упростить доступ (убрать student-session lock), страница доски рендерит новый шаблон; добавить `whiteboard_verify_ai`.
- `core/models.py` — добавить поля под ИИ-вердикт к `WhiteboardSession`.
- `core/templates/core/board.html` — заменить на V2 (Konva) **или** создать новый `board_v2.html` и переключить view.
- `core/tests/test_whiteboard_access.py` — обновить под новый доступ.

**Create:**
- `examprep/routing.py` — websocket routes.
- `core/consumers.py` — `WhiteboardConsumer` (Channels).
- `core/tests/test_whiteboard_ws.py` — тест realtime через `WebsocketCommunicator`.
- `core/migrations/0054_whiteboard_ai_fields.py` — миграция полей AI.
- `core/migrations/0055_purge_whiteboards.py` — data migration: удалить все старые `WhiteboardEvent` и `WhiteboardSession`.

---

### Task 1: Добавить зависимости и базовую настройку Channels (без функционала доски)

**Files:**
- Modify: `requirements.txt`
- Modify: `examprep/settings.py`
- Modify: `examprep/asgi.py`
- Create: `examprep/routing.py`

- [ ] **Step 1: Добавить зависимости**

В `requirements.txt` добавить в конец (версии фиксируем):

```txt
channels==4.1.0
channels-redis==4.2.0
daphne==4.1.2
redis==5.0.8
```

- [ ] **Step 2: Настроить settings**

В `examprep/settings.py`:
1) Добавить `"channels"` в `INSTALLED_APPS` (после `django.contrib.staticfiles`):

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "channels",
    # allauth...
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.vk",
    "core",
]
```

2) Добавить:

```python
ASGI_APPLICATION = "examprep.asgi.application"
```

3) Добавить `CHANNEL_LAYERS` (Redis host/port из env):

```python
REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [(REDIS_HOST, REDIS_PORT)]},
    }
}
```

- [ ] **Step 3: Создать websocket routing**

Создать `examprep/routing.py`:

```python
from django.urls import re_path

from core.consumers import WhiteboardConsumer

websocket_urlpatterns = [
    re_path(r"^ws/board/(?P<session_id>\\d+)/$", WhiteboardConsumer.as_asgi()),
]
```

- [ ] **Step 4: Обновить ASGI application**

В `examprep/asgi.py` заменить содержимое на:

```python
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

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

- [ ] **Step 5: Run sanity check**

Run:
```bash
python -m pip install -r requirements.txt --break-system-packages
python manage.py check
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt examprep/settings.py examprep/asgi.py examprep/routing.py
git commit -m "feat: add django channels + redis channel layer"
```

---

### Task 2: Упростить доступ к доске и удалить polling endpoints V1

**Files:**
- Modify: `core/views.py` (whiteboard_* функции)
- Modify: `core/urls.py`
- Modify: `core/tests/test_whiteboard_access.py`

- [ ] **Step 1: Удалить student-session lock**

В `core/views.py`:
1) Удалить/не использовать:
   - `_student_whiteboard_unlocked`
   - `_student_whiteboard_current_session_id`
   - `_student_whiteboard_set_current_session_id`
   - проверки в `whiteboard_page`, `whiteboard_list`, `whiteboard_create`, `whiteboard_save`.

Новая логика должна быть симметричной:

```python
def _can_access_whiteboard_session(user: User, session: WhiteboardSession):
    if user.role == "student":
        return session.student_id == user.id
    if user.role == "tutor":
        return session.tutor_id == user.id
    if user.role == "admin":
        return True
    return False
```

`whiteboard_list`:
- для student: `student_id` в query должен совпадать с user.id, иначе 403;
- для tutor: student_id должен быть его учеником (как сейчас), иначе 403.

`whiteboard_create`:
- student/tutor могут создать доску, если `_can_access_assignment_task(...)` true.

- [ ] **Step 2: Удалить endpoints polling**

В `core/urls.py` удалить:
- `whiteboard_events_pull`
- `whiteboard_events_append`

И убедиться, что нигде в шаблонах/JS они не используются (после замены board.html).

- [ ] **Step 3: Обновить тесты доступа (сначала сделать падающий тест)**

В `core/tests/test_whiteboard_access.py`:
- убрать `whiteboard_unlocked` из сессии в `test_student_can_open_own_board_page`.

Ожидание: student может открыть свою доску без предварительных session флагов.

Run:
```bash
python manage.py test core.tests.test_whiteboard_access -v 2
```
Expected: FAIL на текущей логике (пока lock ещё есть).

- [ ] **Step 4: Реализовать изменения и прогнать тест**

После правок `views.py`:

Run:
```bash
python manage.py test core.tests.test_whiteboard_access -v 2
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/urls.py core/tests/test_whiteboard_access.py
git commit -m "fix: simplify whiteboard access and remove V1 polling endpoints"
```

---

### Task 3: Реализовать WebSocket consumer для доски (realtime broadcast)

**Files:**
- Create: `core/consumers.py`
- Test: `core/tests/test_whiteboard_ws.py`

- [ ] **Step 1: Написать падающий WS-тест**

Создать `core/tests/test_whiteboard_ws.py`:

```python
import asyncio
import json

from django.test import TransactionTestCase
from django.urls import reverse

from channels.testing import WebsocketCommunicator

from examprep.asgi import application
from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User, TaskVariant, WhiteboardSession


class WhiteboardWebsocketTests(TransactionTestCase):
    async def _connect(self, user, session_id):
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
        session = WhiteboardSession.objects.create(student=student, tutor=tutor, assignment=assignment, task=task, snapshot_json='{"version":2,"objects":[]}')

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
```

Run:
```bash
python manage.py test core.tests.test_whiteboard_ws -v 2
```
Expected: FAIL (нет consumer/маршрута/Channels).

- [ ] **Step 2: Реализовать consumer**

Создать `core/consumers.py`:

```python
import json

from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from core.models import WhiteboardSession, User


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

        try:
            session = await WhiteboardSession.objects.select_related("student", "tutor").aget(id=self.session_id)
        except Exception:
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

        # минимальная валидация формата
        msg_type = (data.get("type") or "")[:64]
        client_id = (data.get("client_id") or "")[:128]
        seq = int(data.get("seq") or 0)
        payload = data.get("payload") or {}

        # broadcast всем
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "board.event",
                "event": {"type": msg_type, "client_id": client_id, "seq": seq, "payload": payload},
            },
        )

    async def board_event(self, event):
        await self.send(text_data=json.dumps(event.get("event") or {}, ensure_ascii=False))
```

- [ ] **Step 3: Прогнать WS-тест**

Run:
```bash
python manage.py test core.tests.test_whiteboard_ws -v 2
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add core/consumers.py core/tests/test_whiteboard_ws.py examprep/routing.py examprep/asgi.py
git commit -m "feat: add whiteboard websocket consumer"
```

---

### Task 4: Миграции — AI поля + удаление всех старых досок/событий

**Files:**
- Modify: `core/models.py`
- Create: `core/migrations/0054_whiteboard_ai_fields.py`
- Create: `core/migrations/0055_purge_whiteboards.py`

- [ ] **Step 1: Добавить поля в модель**

В `core/models.py` в `WhiteboardSession` добавить:

```python
    ai_score = models.IntegerField(null=True, blank=True)
    ai_max_score = models.IntegerField(null=True, blank=True)
    ai_feedback = models.TextField(blank=True, null=True)
    ai_last_verify_at = models.DateTimeField(null=True, blank=True)
    ai_verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="whiteboard_ai_verified")
```

- [ ] **Step 2: Создать миграции**

Run:
```bash
python manage.py makemigrations core -n whiteboard_ai_fields
```

Затем создать data migration `0055_purge_whiteboards.py` (вручную) с удалением данных:

```python
from django.db import migrations


def purge_whiteboards(apps, schema_editor):
    WhiteboardEvent = apps.get_model("core", "WhiteboardEvent")
    WhiteboardSession = apps.get_model("core", "WhiteboardSession")
    WhiteboardEvent.objects.all().delete()
    WhiteboardSession.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0054_whiteboard_ai_fields"),
    ]

    operations = [
        migrations.RunPython(purge_whiteboards, reverse_code=migrations.RunPython.noop),
    ]
```

- [ ] **Step 3: Прогнать миграции в тестовом окружении**

Run:
```bash
python manage.py migrate
```

- [ ] **Step 4: Commit**

```bash
git add core/models.py core/migrations/0054_whiteboard_ai_fields.py core/migrations/0055_purge_whiteboards.py
git commit -m "feat: add whiteboard AI fields and purge legacy boards"
```

---

### Task 5: Новая страница доски V2 на Konva (без ИИ), включая pressure и карточку условия

**Files:**
- Modify: `core/views.py` (`whiteboard_page`, `whiteboard_save`)
- Modify: `core/templates/core/board.html` (заменить целиком на V2)

- [ ] **Step 1: Упростить server-side контекст**

В `whiteboard_page` передавать:
- `session`
- `task_html` (как сейчас)
- `solution_html` (как сейчас, только tutor/admin)
- `snapshot_json` (как строка JSON; если пусто — стартовый `{"version":2,...}`).
- `ws_url` вида `/ws/board/<id>/` (собираем в шаблоне).

Если `session.snapshot_json` пустой — подставить:

```python
session.snapshot_json = json.dumps({"version": 2, "stage": {"scale": 1.0, "x": 0, "y": 0}, "task_card": {"x": 32, "y": 32, "w": 620, "h": 320, "scale": 1.0}, "objects": []}, ensure_ascii=False)
```

- [ ] **Step 2: Заменить `core/templates/core/board.html` на V2**

Шаблон должен:
- подключать Konva CDN:
  - `<script src="https://unpkg.com/konva@9.3.18/konva.min.js"></script>`
- создать контейнер:
  - `<div id="board-stage" class="relative w-full h-[70vh] bg-white"></div>`
- создать overlay карточку:
  - `<div id="task-card-overlay" class="absolute ...">...</div>`
  - drag/resize (минимум: ручка в правом нижнем углу + pointer events)
- открыть WebSocket:
  - `const ws = new WebSocket((location.protocol==='https:'?'wss':'ws') + '://' + location.host + '/ws/board/{{ session.id }}/');`
- иметь `clientId = crypto.randomUUID()` fallback на рандом.
- иметь echo suppression: если `msg.client_id === clientId` → не применять.
- рисование:
  - pen: хранит текущий stroke с точками `{x,y,p}`; отправляет WS:
    - `stroke_start`, затем batched `stroke_points` каждые 30-50мс, затем `stroke_end`.
  - pressure: `evt.pressure` для pen; для mouse ставим `p=0.5`.
  - рендер stroke: кастомный `Konva.Shape` с `sceneFunc(ctx, shape)`:
    - пройти по сегментам и рисовать line segments с шириной `baseWidth * (0.3 + p)` (минимум).
    - round caps.
- сохранение:
  - `POST /board/{{ session.id }}/save/` body `{snapshot_json: JSON.stringify(state)}`
  - autosave debounce 10-20 секунд.

- [ ] **Step 3: Добавить smoke-тест страницы доски**

В `core/tests/test_whiteboard_access.py` дополнить `test_tutor_can_open_own_student_board_page` проверкой, что в HTML есть `konva` или `board-stage`:

```python
self.assertContains(r, "board-stage")
```

Run:
```bash
python manage.py test core.tests.test_whiteboard_access -v 2
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/templates/core/board.html core/tests/test_whiteboard_access.py
git commit -m "feat: replace whiteboard UI with konva v2 + websocket sync"
```

---

### Task 6: Endpoint ИИ проверки доски (баллы + комментарий) + отображение результата

**Files:**
- Modify: `core/urls.py`
- Modify: `core/views.py`
- Modify: `core/templates/core/board.html`
- Test: `core/tests/test_whiteboard_ai_verify.py` (new)

- [ ] **Step 1: URL**

В `core/urls.py` добавить:

```python
path("board/<int:session_id>/verify-ai/", views.whiteboard_verify_ai, name="whiteboard_verify_ai"),
```

- [ ] **Step 2: Написать падающий тест прав доступа**

Создать `core/tests/test_whiteboard_ai_verify.py`:

```python
import base64

from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User, TaskVariant, WhiteboardSession


class WhiteboardAiVerifyTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="tutor1", password="x", role="tutor")
        self.student = User.objects.create_user(username="student1", password="x", role="student")
        self.tutor.students.add(self.student)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=13, name="Развернутая", max_points=3, is_extended_answer=True)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="", difficulty=30, exam_points=3)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Условие</p>", solution="<p>Решение</p>")
        assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="Вариант", is_draft=False)
        assignment.tasks.add(task)
        self.session = WhiteboardSession.objects.create(student=self.student, tutor=self.tutor, assignment=assignment, task=task, snapshot_json='{"version":2,"objects":[]}')

    def test_student_cannot_verify_ai(self):
        self.client.login(username="student1", password="x")
        url = reverse("whiteboard_verify_ai", args=[self.session.id])
        r = self.client.post(url, data={"image_data_url": "data:image/png;base64,"})
        self.assertEqual(r.status_code, 403)
```

Run:
```bash
python manage.py test core.tests.test_whiteboard_ai_verify -v 2
```
Expected: FAIL (нет view/route).

- [ ] **Step 3: Реализовать `whiteboard_verify_ai`**

В `core/views.py` добавить:
- права: только tutor/admin; tutor должен совпадать с `session.tutor`.
- cooldown: 120 секунд, поле `session.ai_last_verify_at`.
- вход: `image_data_url` (data:image/png;base64,...).
- prompt: аналогичен `api_tutor_verify_with_ai`, но:
  - “Оцени решение по изображению доски”
  - максимум = `max(task.exam_points, task.task_type.max_points)`
  - вернуть JSON: `primary_score`, `is_correct`, `feedback`.
- вызов OpenRouter: копируем безопасный JSON-parsing и latex-repair из `api_tutor_verify_with_ai`.
- сохраняем:
  - `session.ai_score`, `session.ai_max_score`, `session.ai_feedback`, `session.ai_last_verify_at`, `session.ai_verified_by`
- ответ: `{status:"ok", primary_score, feedback, feedback_html, is_correct, cooldown_seconds}`

- [ ] **Step 4: UI**

В `board.html`:
- кнопка “Проверить доску ИИ” (видна обоим, но disabled для student + tooltip “только репетитор”).
- при клике:
  - экспорт Konva stage `stage.toDataURL({pixelRatio: 2})`
  - POST на `/board/<id>/verify-ai/`
  - показать блок “Вердикт ИИ” с баллами + HTML (используем `feedback_html`).
- кнопка “Перепроверить” у репетитора, учитывая `retry_after` (429) как у других verify.

- [ ] **Step 5: Дописать тест для tutor (с моком requests.post)**

В тесте добавить:
- `@patch("core.views.requests.post")` и вернуть JSON как в существующих тестах verify-ai.
- ожидать 200 и что `session.ai_score` обновился.

- [ ] **Step 6: Commit**

```bash
git add core/urls.py core/views.py core/templates/core/board.html core/tests/test_whiteboard_ai_verify.py
git commit -m "feat: add whiteboard AI verification (score + feedback)"
```

---

### Task 7: Финальная чистка V1 кода и прогон тестов

**Files:**
- Modify: `core/views.py` — удалить мёртвые V1 функции/вспомогалки.
- Modify: `core/urls.py` — убедиться что pull/append отсутствуют.
- Optional: `core/models.py` — можно оставить `WhiteboardEvent` как таблицу “на будущее”, но не использовать.

- [ ] **Step 1: Найти и удалить ссылки на V1 endpoints**

Run:
```bash
python - <<'PY'
import re, pathlib
root = pathlib.Path("core")
pat = re.compile(r"/events/(pull|append)/")
hits = []
for p in root.rglob("*.html"):
    t = p.read_text("utf-8", errors="ignore")
    if pat.search(t):
        hits.append(str(p))
print("\\n".join(hits))
PY
```
Expected: пусто.

- [ ] **Step 2: Полный прогон тестов**

Run:
```bash
python manage.py test core.tests -v 1
```
Expected: PASS.

- [ ] **Step 3: Commit (если были финальные правки)**

```bash
git add core/views.py core/urls.py core/templates/core/board.html
git commit -m "chore: remove legacy whiteboard v1 remnants"
```

---

## Self-review

Покрытие спеки:
- удаление V1 endpoints + новый Konva UI + WS realtime → Tasks 2,3,5 ✅
- устранение проблемы “репетитор не может стартовать” → Task 2 ✅
- pressure и отсутствие “пропадания” → Task 5 (echo suppression + pressure points) ✅
- карточка условия на холсте (scale/resize) → Task 5 ✅
- ИИ проверка с повторной перепроверкой и видимостью для обоих → Task 6 ✅
- удаление старых досок/событий → Task 4 ✅

---

## Execution choice

План сохранён в `docs/superpowers/plans/2026-05-14-whiteboard-v2-konva-channels.md`.

Два варианта выполнения:
1) **Subagent-Driven (recommended)**
2) **Inline Execution (executing-plans)**

Какой вариант выбираете?

