# Дизайн: Whiteboard V2 (Konva.js + Django Channels + Redis) + удаление V1

Дата: 2026-05-14  
Затрагиваемое: интерактивная доска для совместной работы ученик↔репетитор

## Контекст и проблема

Текущая доска (V1) реализована как SVG + частый polling (`/events/pull` / `/events/append`) и шлёт `set_object` на каждое движение пера. Это приводит к:
- сильным лагам (высокая частота событий + большой payload),
- «миганию»/откатам штрихов (эхо собственных событий + order-by-id),
- плохому UX пера на планшете (pressure практически не используется),
- проблеме “репетитор не может стартовать доску” из-за локдауна на стороне student session.

Решение: полностью заменить доску на V2:
- **Konva.js (Canvas)** для быстрого рисования,
- **WebSocket** через **Django Channels + Redis** для realtime,
- **удалить V1** (UI/эндпоинты/события) и **удалить все старые доски** в БД.

## Цели

1) Совместное рисование без лагов: репетитор и ученик видят изменения почти мгновенно.  
2) Репетитор может **создать (стартовать)** доску, ученик может подключиться. И наоборот.  
3) Поддержка **силы нажатия (pressure)** на планшете.  
4) Никаких «пропаданий последнего кусочка» при отрыве стилуса.  
5) Условие задачи масштабируется как **карточка на холсте** (draggable + resizable).  
6) У репетитора остаётся кнопка “Решение” (панель).  
7) Добавить “Проверить доску ИИ”:
   - запускает только репетитор,
   - результат (баллы + комментарий) видят ученик и репетитор,
   - возможность повторной перепроверки (cooldown).
8) Удалить V1 и все данные V1 досок в БД (по запросу пользователя).

## Не цели

- Миграция/конвертация старых досок (пользователь выбрал “удалить всё”).  
- Оффлайн-режим или “истинная CRDT” синхронизация (реалтайм делаем через WS + серверный broadcast; без сложной OT/CRDT на первом этапе).

## Архитектура

### Компоненты

1) **Django view** `whiteboard_page(session_id)` — отдаёт HTML страницы доски V2 и snapshot.  
2) **WebSocket consumer** `WhiteboardConsumer` (Channels) — join group `whiteboard_<session_id>`, принимает события, валидирует доступ, broadcast в группу.  
3) **Redis channel layer** — транспорт WS-сообщений между воркерами.  
4) **Snapshot storage**: `WhiteboardSession.snapshot_json` хранит полное состояние V2.  
5) **AI verify endpoint** `POST /board/<session_id>/verify-ai/` — создаёт PNG холста, отправляет в текущий AI pipeline, сохраняет вердикт в session.

### Модель данных (V2)

Остаётся `WhiteboardSession`, меняется смысл `snapshot_json`:

```json
{
  "version": 2,
  "stage": { "scale": 1.0, "x": 0, "y": 0 },
  "task_card": { "x": 32, "y": 32, "w": 620, "h": 320, "scale": 1.0 },
  "objects": [
    {
      "id": "stroke_...",
      "type": "stroke",
      "color": "#111827",
      "baseWidth": 4,
      "points": [{"x":10,"y":20,"p":0.2}, {"x":12,"y":23,"p":0.4}]
    },
    {
      "id": "shape_...",
      "type": "rect",
      "x": 100, "y": 120, "w": 200, "h": 120,
      "stroke": "#2563eb", "width": 4
    }
  ],
  "ai": {
    "score": 7,
    "max_score": 10,
    "feedback": "…",
    "verified_at": "2026-05-14T12:00:00Z",
    "verified_by": 123
  }
}
```

#### Удаление `WhiteboardEvent`

В V2 **не используем** инкрементальную таблицу событий в БД. События идут по WS и применяются сразу, а “истина” периодически фиксируется snapshot’ом:
- авто-сохранение раз в N секунд (например 10–20с) или debounce после паузы;
- ручное сохранение.

Это резко снижает нагрузку на БД и убирает накопление миллионов событий.

## Протокол realtime (WebSocket)

### Сообщения от клиента → сервер

Каждое сообщение имеет:
- `type`
- `session_id`
- `client_id` (UUID вкладки)
- `seq` (монотонный локальный счётчик для клиента; для диагностики/дедупа при необходимости)
- `payload`

Примеры:

`stroke_start`
```json
{"type":"stroke_start","session_id":12,"client_id":"...","seq":1,"payload":{"id":"stroke_1","color":"#111827","baseWidth":4,"x":10,"y":20,"p":0.2}}
```

`stroke_points` (батч)
```json
{"type":"stroke_points","session_id":12,"client_id":"...","seq":2,"payload":{"id":"stroke_1","points":[{"x":11,"y":21,"p":0.3},{"x":12,"y":23,"p":0.4}]}}
```

`stroke_end`
```json
{"type":"stroke_end","session_id":12,"client_id":"...","seq":3,"payload":{"id":"stroke_1"}}
```

`object_add|object_update|object_delete` — для фигур/таблиц

`task_card_set`
```json
{"type":"task_card_set","session_id":12,"client_id":"...","seq":10,"payload":{"x":40,"y":40,"w":800,"h":420,"scale":1.2}}
```

### Сервер → всем клиентам в группе

Сервер ретранслирует событие “как есть”, добавляя `server_ts` и `author_id`.

Клиент **не применяет** сообщения, где `client_id == myClientId` (echo suppression), чтобы избежать “миганий”.

## UI/UX (Konva)

### Canvas layer

- Konva `Stage` + `Layer` для рисования.
- Инструменты:
  - pen (pressure stroke),
  - eraser (удаление stroke/shape по hit-test),
  - line/rect/triangle,
  - table (быстрая сетка).

### Pressure

Konva Line не поддерживает variable width per point “из коробки”, поэтому stroke рисуем как:
- либо кастомный `Konva.Shape` с ручной отрисовкой по сегментам,
- либо разделяем на маленькие сегменты (дороже).

Цель: визуально соответствовать реальному нажатию пера.

### Карточка условия на холсте

Условие остаётся HTML (MathJax/картинки) — это сложно рисовать “в canvas”.

Делаем карточку как **DOM overlay** поверх `Stage`:
- позиция карточки хранится в “мировых” координатах сцены,
- при пан/зуме сцены пересчитываем CSS transform карточки,
- карточка draggable/resizable (через ручки/resize).

Состояние карточки синхронизируется `task_card_set`.

### Панель “Решение” у репетитора

Остаётся отдельной панелью (как сейчас), не объектом на холсте.

## Endpoints / Routing

### HTTP

Оставляем:
- `GET /board/<session_id>/` — страница доски.
- `GET /board/list/?student_id=...&assignment_id=...&task_id=...` — список досок.
- `POST /board/<assignment_id>/<task_id>/create/` — создание доски.
- `POST /board/<session_id>/save/` — сохранение snapshot.

Добавляем:
- `POST /board/<session_id>/verify-ai/` — ИИ проверка доски (только tutor/admin).

Удаляем:
- `GET /board/<session_id>/events/pull/`
- `POST /board/<session_id>/events/append/`

### WebSocket

WS endpoint (пример): `/ws/board/<session_id>/`

## Доступ и безопасность

- Доступ к доске:
  - student: `session.student_id == request.user.id`
  - tutor: `session.tutor_id == request.user.id`
  - admin: разрешено
- `whiteboard_create`: разрешено tutor/student, если `_can_access_assignment_task` true.
- ИИ-проверка: разрешено tutor/admin (и только если tutor соответствует session).
- Rate-limit/cooldown для verify-ai по аналогии с текущей AI-проверкой решений.

## Удаление V1 и данных

Пользователь выбрал “Удалить всё”.

Требуется миграция данных:
- удалить все `WhiteboardEvent`
- удалить все `WhiteboardSession`

Если хотим оставить `WhiteboardSession` как сущность V2:
- делаем *data migration* которая чистит старые записи перед релизом V2 (все записи считаем V1).

## Инфраструктура / деплой

### Python зависимости

Добавить в `requirements.txt`:
- `channels`
- `channels-redis`
- ASGI сервер (выбор один): `daphne` **или** `uvicorn`

### Django settings

Изменения в `examprep/settings.py`:
- добавить `channels` в `INSTALLED_APPS`
- добавить `ASGI_APPLICATION = "examprep.asgi.application"`
- настроить `CHANNEL_LAYERS` на Redis (host/port из env)

### ASGI routing

Обновить `examprep/asgi.py`:
- `ProtocolTypeRouter` + `URLRouter` с websocket маршрутом `/ws/board/<session_id>/`

### Nginx/Systemd на VPS

Чтобы WS работал, сервис должен быть ASGI (daphne/uvicorn).
Nginx должен проксировать Upgrade headers.

Примечание: текущий GitHub deploy workflow перезапускает `examprep` systemd unit — значит unit нужно обновить на VPS (это будет частью внедрения).

## Тестирование

1) Unit-тесты доступа (обновить `test_whiteboard_access.py` под новую логику без session-lock).  
2) Тест WS:
   - подключение tutor и student к одному session_id,
   - событие от tutor приходит student’у (Channels тестовый коммуникатор).
3) Тест verify-ai permissions:
   - student получает 403,
   - tutor получает 200 (с моками openrouter-клиента).

## Критерии приёмки

- Репетитор может создать доску, ученик открывает и видит realtime изменения.
- Лаги исчезают: нет polling, данные идут через WS.
- Pressure учитывается (штрих заметно тоньше/толще).
- При отрыве стилуса штрих не “пропадает/появляется”.
- Карточка условия масштабируется и синхронизируется.
- ИИ-проверка доски доступна репетитору, выдаёт баллы+комментарий и видна ученику.
- V1 endpoints удалены, старые доски удалены из БД.

