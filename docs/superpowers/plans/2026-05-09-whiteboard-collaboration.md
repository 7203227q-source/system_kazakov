# Collaborative Whiteboard (HTTP Realtime) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить интерактивную векторную доску для каждой задачи ученика с двусторонним вводом (ученик+репетитор), автодобавлением условия на холст, сохранением (кнопка + автосейв) и историей “нескольких досок”.

**Architecture:** MVP синхронизации реализуется на HTTP: клиенты отправляют события рисования, второй клиент подтягивает новые события pull’ом по курсору. Постоянное состояние хранится как `snapshot_json` в `WhiteboardSession`. Протокол событий спроектирован так, чтобы позже перейти на WebSocket без изменения payload.

**Tech Stack:** Django ORM, Django templates, SVG + Pointer Events, fetch, JSON.

---

## File Structure

**Create:**
- `/workspace/core/templates/core/board.html` — страница доски (условие на холсте + SVG + тулбар + список досок).
- `/workspace/core/migrations/0025_whiteboard_models.py` — миграция новых моделей.

**Modify:**
- `/workspace/core/models.py` — модели `WhiteboardSession`, `WhiteboardEvent`.
- `/workspace/core/views.py` — view’ы доски: page/create/list/events/save.
- `/workspace/core/urls.py` — URL’ы для доски.
- `/workspace/core/templates/core/student_solve_assignment.html` — кнопка “Доска” у задач.
- `/workspace/core/templates/core/tutor_assignment_view.html` — кнопка “Доска” у задач.

**Test:**
- `/workspace/core/tests/test_whiteboard_access.py` — доступ и создание досок.

---

### Task 1: Модели WhiteboardSession/WhiteboardEvent + миграция

**Files:**
- Modify: `/workspace/core/models.py`
- Create: `/workspace/core/migrations/0025_whiteboard_models.py`
- Test: `/workspace/core/tests/test_whiteboard_access.py`

- [ ] **Step 1: Добавить модели**

В `core/models.py` добавить (в конец файла, рядом с другими моделями):

```py
class WhiteboardSession(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='whiteboard_sessions_as_student')
    tutor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='whiteboard_sessions_as_tutor')
    assignment = models.ForeignKey('Assignment', on_delete=models.CASCADE, related_name='whiteboard_sessions')
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='whiteboard_sessions')
    title = models.CharField(max_length=120, blank=True, null=True)
    snapshot_json = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['student', 'assignment', 'task', 'created_at']),
        ]


class WhiteboardEvent(models.Model):
    session = models.ForeignKey(WhiteboardSession, on_delete=models.CASCADE, related_name='events')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='whiteboard_events')
    kind = models.CharField(max_length=40)
    payload_json = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
```

- [ ] **Step 2: Миграция**

Создать миграцию вручную (аналогично предыдущим в репо) в `/workspace/core/migrations/0025_whiteboard_models.py` с `CreateModel` для обеих моделей.

- [ ] **Step 3: Тест доступа (каркас)**

Создать `core/tests/test_whiteboard_access.py`:

```py
import pytest
from django.urls import reverse
from core.models import User


@pytest.mark.django_db
def test_student_cannot_open_other_students_session(client):
    s1 = User.objects.create_user(username='s1', password='x', role='student')
    s2 = User.objects.create_user(username='s2', password='x', role='student')
    client.force_login(s1)
    url = reverse('whiteboard_list')
    r = client.get(url, {'student_id': s2.id, 'assignment_id': 1, 'task_id': 1})
    assert r.status_code in (302, 403, 404)
```

Этот тест далее будет уточнён после добавления эндпоинтов.

- [ ] **Step 4: Commit**

```bash
git add core/models.py core/migrations/0025_whiteboard_models.py core/tests/test_whiteboard_access.py
git commit -m "feat: add whiteboard session and event models"
```

---

### Task 2: URL’ы и доступ (create/list/page)

**Files:**
- Modify: `/workspace/core/urls.py`
- Modify: `/workspace/core/views.py`

- [ ] **Step 1: Добавить URL’ы**

В `core/urls.py` добавить:

```py
path('board/<int:session_id>/', views.whiteboard_page, name='whiteboard_page'),
path('board/list/', views.whiteboard_list, name='whiteboard_list'),
path('board/<int:assignment_id>/<int:task_id>/create/', views.whiteboard_create, name='whiteboard_create'),
path('board/<int:session_id>/events/pull/', views.whiteboard_events_pull, name='whiteboard_events_pull'),
path('board/<int:session_id>/events/append/', views.whiteboard_events_append, name='whiteboard_events_append'),
path('board/<int:session_id>/save/', views.whiteboard_save, name='whiteboard_save'),
```

- [ ] **Step 2: Хелперы прав доступа**

В `core/views.py` добавить helper:

```py
def can_access_whiteboard(user, session: WhiteboardSession):
    if user.role == 'student':
        return session.student_id == user.id
    if user.role == 'tutor':
        return session.tutor_id == user.id
    if user.role == 'admin':
        return True
    return False
```

И helper для доступа по assignment/task:

```py
def can_access_assignment_task(user, assignment: Assignment, task: Task, student: User):
    if user.role == 'student':
        return assignment.student_id == user.id and assignment.student_id == student.id
    if user.role == 'tutor':
        return assignment.tutor_id == user.id and assignment.student_id == student.id
    if user.role == 'admin':
        return True
    return False
```

- [ ] **Step 3: Реализовать `whiteboard_list`**

```py
@login_required
def whiteboard_list(request):
    student_id = int(request.GET.get('student_id') or 0)
    assignment_id = int(request.GET.get('assignment_id') or 0)
    task_id = int(request.GET.get('task_id') or 0)
    student = get_object_or_404(User, id=student_id, role='student')
    assignment = get_object_or_404(Assignment, id=assignment_id, is_draft=False)
    task = get_object_or_404(Task, id=task_id)
    if not can_access_assignment_task(request.user, assignment, task, student):
        return JsonResponse({'error': 'forbidden'}, status=403)
    sessions = WhiteboardSession.objects.filter(student=student, assignment=assignment, task=task).order_by('-created_at')[:50]
    return JsonResponse({'sessions': [{'id': s.id, 'title': s.title or f'Доска {s.id}', 'created_at': s.created_at.isoformat()} for s in sessions]})
```

- [ ] **Step 4: Реализовать `whiteboard_create`**

```py
@login_required
@require_POST
def whiteboard_create(request, assignment_id, task_id):
    assignment = get_object_or_404(Assignment, id=assignment_id, is_draft=False)
    task = get_object_or_404(Task, id=task_id)
    student = assignment.student
    if not can_access_assignment_task(request.user, assignment, task, student):
        return JsonResponse({'error': 'forbidden'}, status=403)
    session = WhiteboardSession.objects.create(
        student=student,
        tutor=assignment.tutor,
        assignment=assignment,
        task=task,
        title=None,
        snapshot_json=None,
    )
    return JsonResponse({'session_id': session.id})
```

- [ ] **Step 5: Реализовать `whiteboard_page` (каркас)**

```py
@login_required
def whiteboard_page(request, session_id):
    session = get_object_or_404(WhiteboardSession.objects.select_related('student', 'tutor', 'assignment', 'task'), id=session_id)
    if not can_access_whiteboard(request.user, session):
        return redirect('login')
    theme = session.student.preferred_theme or 'classic'
    task_html = session.task.get_content_for_theme(theme)
    solution_html = session.task.get_solution_for_theme(theme) if request.user.role in ['tutor', 'admin'] else ''
    return render(request, 'core/board.html', {
        'session': session,
        'task_html': task_html,
        'solution_html': solution_html,
    })
```

- [ ] **Step 6: Smoke-check**

```bash
python -m compileall -q /workspace/core
```

- [ ] **Step 7: Commit**

```bash
git add core/urls.py core/views.py
git commit -m "feat: add whiteboard endpoints (page/create/list)"
```

---

### Task 3: Страница доски (SVG), инструменты, “условие как объект”

**Files:**
- Create: `/workspace/core/templates/core/board.html`

- [ ] **Step 1: Разметка**

В `board.html`:
- header: название, кнопки “Сохранить”, “Новая доска”, dropdown выбора доски.
- тулбар: pen/eraser/line/rect/triangle/table, цвета, толщина.
- холст: `<svg id="wb-canvas" ...></svg>`

Передать в JS:
- `sessionId`
- `initialSnapshot` (`session.snapshot_json`)
- `taskHtml` (условие) — будет упаковано в объект `task_card` на холсте, если его нет.

- [ ] **Step 2: Рендер объектов**

JS функции:

```js
function render(state) { /* пересобирает SVG */ }
function upsertObject(obj) { /* state.objects[id]=obj */ }
function deleteObject(id) { /* удалить */ }
```

`task_card`:
- вставить как `<foreignObject>` внутри SVG с HTML условием
- позицию/размер хранить в объекте (`x,y,w,h`)

- [ ] **Step 3: Pointer Events (pen)**

Рисование от руки:
- на pointerdown: начать stroke, создать объект `{type:'pen', points:[...] }`
- на pointermove: добавлять точки (батчить в событие `stroke_points`)
- на pointerup: `stroke_end`

- [ ] **Step 4: Фигуры + таблица**

Упрощённо:
- line/rect/triangle: создаются “drag to size” (down=start, move=preview, up=commit).
- table: по клику вставляем таблицу с preset (например 4x4), можно позже расширять.

- [ ] **Step 5: Сохранение и автосейв**

- `Save` делает `POST /board/<session_id>/save/` с `snapshot_json`.
- автосейв: `setInterval` (45–60 сек) + `beforeunload` (если dirty).

- [ ] **Step 6: Commit**

```bash
git add core/templates/core/board.html
git commit -m "feat: add whiteboard page with svg canvas and task card"
```

---

### Task 4: Realtime на HTTP (append/pull) + применение событий

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/board.html`

- [ ] **Step 1: Pull**

```py
@login_required
def whiteboard_events_pull(request, session_id):
    session = get_object_or_404(WhiteboardSession, id=session_id)
    if not can_access_whiteboard(request.user, session):
        return JsonResponse({'error': 'forbidden'}, status=403)
    after = int(request.GET.get('after') or 0)
    qs = WhiteboardEvent.objects.filter(session=session, id__gt=after).select_related('author').order_by('id')[:500]
    return JsonResponse({'events': [{'id': e.id, 'kind': e.kind, 'payload': e.payload_json, 'author_id': e.author_id} for e in qs]})
```

- [ ] **Step 2: Append (batch)**

```py
@login_required
@require_POST
def whiteboard_events_append(request, session_id):
    session = get_object_or_404(WhiteboardSession, id=session_id)
    if not can_access_whiteboard(request.user, session):
        return JsonResponse({'error': 'forbidden'}, status=403)
    body = json.loads(request.body.decode('utf-8') or '{}')
    events = body.get('events') or []
    created = []
    for e in events[:200]:
        kind = (e.get('kind') or '')[:40]
        payload = json.dumps(e.get('payload') or {}, ensure_ascii=False)
        obj = WhiteboardEvent.objects.create(session=session, author=request.user, kind=kind, payload_json=payload)
        created.append(obj.id)
    return JsonResponse({'ids': created})
```

- [ ] **Step 3: Применение событий в JS**

В `board.html`:
- локальная очередь событий (outbox)
- `append` раз в 200–400мс отправляет батч
- `pull` раз в 300–800мс тянет новые (cursor=lastId)
- `applyEvent(kind,payload)` обновляет state и рендерит

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/templates/core/board.html
git commit -m "feat: add http realtime sync for whiteboard"
```

---

### Task 5: API сохранения snapshot + автодобавление task_card

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/board.html`

- [ ] **Step 1: Save endpoint**

```py
@login_required
@require_POST
def whiteboard_save(request, session_id):
    session = get_object_or_404(WhiteboardSession, id=session_id)
    if not can_access_whiteboard(request.user, session):
        return JsonResponse({'error': 'forbidden'}, status=403)
    body = json.loads(request.body.decode('utf-8') or '{}')
    snapshot = body.get('snapshot_json')
    if not isinstance(snapshot, str):
        return JsonResponse({'error': 'bad_request'}, status=400)
    session.snapshot_json = snapshot
    session.save(update_fields=['snapshot_json', 'updated_at'])
    return JsonResponse({'status': 'ok'})
```

- [ ] **Step 2: Автодобавление task_card**

В JS при загрузке:
- если `task_card` отсутствует в `snapshot_json`, создать объект `task_card` с `content_html` = `taskHtml` и вставить в state.
- зафиксировать его через `Save` (один раз) или через событие `set_object`.

- [ ] **Step 3: Commit**

```bash
git add core/views.py core/templates/core/board.html
git commit -m "feat: add whiteboard save and auto task card insertion"
```

---

### Task 6: Точки входа “Доска” у задачи (ученик и репетитор)

**Files:**
- Modify: `/workspace/core/templates/core/student_solve_assignment.html`
- Modify: `/workspace/core/templates/core/tutor_assignment_view.html`
- Modify: `/workspace/core/views.py` (необязательно: helper URL/создание по клику)

- [ ] **Step 1: Кнопка в student_solve_assignment**

Добавить рядом с задачей кнопку:
- делает `POST /board/<assignment_id>/<task_id>/create/` (fetch с CSRF),
- после ответа редиректит в `/board/<session_id>/`.

- [ ] **Step 2: Кнопка в tutor_assignment_view**

Аналогично, но открывает доску для того же assignment/task.

- [ ] **Step 3: Smoke-check**

```bash
python -m compileall -q /workspace/core
```

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/student_solve_assignment.html core/templates/core/tutor_assignment_view.html
git commit -m "feat: add open whiteboard buttons for student and tutor"
```

---

### Task 7: Уточнить тесты доступа

**Files:**
- Modify: `/workspace/core/tests/test_whiteboard_access.py`

- [ ] **Step 1: Добавить фикстуры на assignment/task/session**

Создать student/tutor, assignment с ними, task, session и проверить:
- student видит только свой session
- tutor видит только sessions своих учеников
- чужой tutor получает 403 на pull/append/save

- [ ] **Step 2: Run tests**

```bash
pytest -q
```

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_whiteboard_access.py
git commit -m "test: add whiteboard access tests"
```

---

### Task 8: Push

- [ ] **Step 1: Push**

```bash
git push origin main
```

