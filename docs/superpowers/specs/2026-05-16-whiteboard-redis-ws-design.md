# Collaborative Whiteboard (Redis + WebSocket) Design

**Goal:** Заменить текущую HTTP+БД синхронизацию доски на WebSocket-синхронизацию через Redis, чтобы убрать лаги, снизить нагрузку на БД и сделать ввод “живым” для ученика и репетитора.

**Non-goals:**
- Не переписывать UI доски и инструменты рисования (pen/eraser/line/rect/triangle/table) — меняем транспорт синхронизации и минимально адаптируем клиент.
- Не вводить долговременный аудит/историю всех событий в БД на каждом движении пера.

---

## Current State (Problems)

Текущая реализация синхронизации использует:
- `POST /board/<session_id>/events/append/` — пишет события в БД (каждый event отдельной ORM-вставкой).
- `GET /board/<session_id>/events/pull/?after=<id>` — клиент поллит новые события.
- `render()` выполняется часто и пересобирает весь SVG.

Это приводит к лагам и лишней нагрузке на БД, особенно при рисовании пером, где событий много.

---

## Proposed Architecture

### Transport

Основной транспорт синхронизации — WebSocket:
- URL: `/ws/board/<session_id>/`
- Реализация: Django Channels (ASGI) + Redis channel layer
- Nginx проксирует WebSocket к ASGI-серверу.

### Persistence Model

Хранение разделяется на два слоя:
- **PostgreSQL/SQLite (DB):** остаётся “источник правды” для `WhiteboardSession.snapshot_json` (кнопка “Сохранить” и автосейв).
- **Redis (ephemeral):** хранит недавние события для реконнекта/догонялки, с TTL.

Такой баланс сохраняет возможность открыть доску и увидеть состояние даже после рестарта Redis, но избегает записи каждого pointermove в БД.

### Event Ordering

Порядок событий в сессии задаётся сервером через Redis `INCR`:
- key: `wb:{session_id}:seq`
- каждое принятое событие (или батч) получает возрастающие `server_id` (монотонный курсор для sync).

### Redis Keys

- `wb:{session_id}:seq` — инкрементный счётчик событий.
- `wb:{session_id}:events` — Redis list последних событий (JSON-строки).
- TTL:
  - `wb:{session_id}:seq`: TTL не обязателен (можно держать, можно удалять вместе с events).
  - `wb:{session_id}:events`: TTL обязателен (например 6–24 часа).
- Ограничение размера:
  - `LTRIM` до лимита (например 10_000 событий) чтобы контролировать память.

---

## Protocol

### Client → Server messages

1) `event_batch`

```json
{
  "type": "event_batch",
  "events": [
    { "kind": "set_object", "payload": { "object": { "...": "..." } }, "client_id": "c_..." },
    { "kind": "delete_object", "payload": { "id": "..." }, "client_id": "c_..." }
  ]
}
```

Notes:
- `client_id` используется только для диагностики/идемпотентности на клиенте (сервер не гарантирует дедупликацию).
- Сервер добавляет `author_id` из `scope["user"]`.

2) `sync`

```json
{ "type": "sync", "after_server_id": 1234 }
```

Если Redis events ещё живы по TTL, сервер возвращает все события с `server_id > after_server_id`. Если нет — сервер сигнализирует, что нужен full reload (snapshot).

### Server → Client messages

1) `events`

```json
{
  "type": "events",
  "events": [
    { "server_id": 1235, "kind": "set_object", "payload": { "...": "..." }, "author_id": 10 }
  ]
}
```

2) `sync_result`

```json
{
  "type": "sync_result",
  "events": [ ... ],
  "need_snapshot": false
}
```

Если Redis не содержит нужного диапазона:

```json
{ "type": "sync_result", "events": [], "need_snapshot": true }
```

---

## Access Control

На этапе WebSocket connect:
- Загружаем `WhiteboardSession` по `session_id`.
- Проверяем `_can_access_whiteboard_session(user, session)` (та же логика доступа, что и для HTTP).
- Для student дополнительно проверяем ограничения “unlocked/current session” (если они включены).
- При ошибке: close connection (код 4403).

---

## Client Changes (board.html)

- Убрать `pullLoop` и `flushLoop`.
- Поднять один WebSocket:
  - `ws(s)://<host>/ws/board/<session_id>/`
  - При connect: отправить `sync` с последним `server_id` (0 при старте).
- Буферизация отправки:
  - Собирать `pending` локально.
  - Отправлять пачками каждые 20–50мс или по достижению размера (например 50 событий).
- Обработка входящих:
  - Для каждого event вызвать `applyEvent(kind, payload)` как сейчас.
  - Обновлять `lastServerId`.
- Snapshot:
  - `saveSnapshot()` оставить через HTTP `POST /board/<session_id>/save/`.
  - Автосейв — оставить, но можно увеличить интервал (например 30–60 сек) и сохранять только если dirty.

---

## Server Changes (Django)

- Добавить зависимости:
  - `channels`
  - `channels-redis`
  - ASGI сервер: `uvicorn` или `daphne` (выбор на этапе реализации)
- Изменить `settings.py`:
  - добавить `"channels"` в `INSTALLED_APPS`
  - добавить `ASGI_APPLICATION = "examprep.asgi.application"`
  - добавить `CHANNEL_LAYERS` с Redis backend и `REDIS_URL`
- Добавить routing:
  - `examprep/routing.py` (websocket_urlpatterns)
  - обновить `examprep/asgi.py` (ProtocolTypeRouter + AuthMiddlewareStack + URLRouter)
- Добавить consumer:
  - `core/consumers.py` (WhiteboardConsumer)
  - Обязанности: auth/access, обработка `event_batch`/`sync`, рассылка в group, запись событий в Redis.
- Добавить минимальные тесты:
  - доступ на connect (403-close)
  - smoke: отправка event_batch от одного клиента приходит второму (channels testing tools)

---

## Deployment (VPS: systemd + nginx)

- Redis:
  - Установить `redis-server`
  - Слушать только `127.0.0.1`
- ASGI:
  - Запуск приложения через systemd unit (uvicorn/daphne)
  - Обновить nginx конфиг:
    - `location /ws/` с WebSocket proxy headers
    - обычный `location /` как ранее для HTTP
- Env:
  - `REDIS_URL=redis://127.0.0.1:6379/0`
  - остальное без изменений

