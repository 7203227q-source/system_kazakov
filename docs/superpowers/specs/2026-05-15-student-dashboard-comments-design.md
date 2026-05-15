# Student Dashboard: Comments Panel + Deep Links — Design

## Context
Сейчас:
- У репетитора на дашборде уже есть список комментариев (последние сообщения) и переход в историю по `submission_id`.
- У ученика на дашборде есть счётчик `unread_tutor_replies_total`, но нет списка комментариев и нет быстрых переходов в конкретные задания.
- `student_history` уже имеет пагинацию, но deep-link `?submission_id=...` пока не поддерживается.
- `student_solve_assignment` (страница решения варианта) рендерит карточки задач с `data-task-id`, но не раскрывает автоматически чат/блок вопросов по deep-link.

## Goal
1) Добавить на **дашборд ученика** блок “Комментарии” со списком последних сообщений и подсветкой непрочитанных ответов репетитора.
2) По клику на комментарий делать переход:
   - если комментарий из варианта: на `/student/assignment/<assignment_id>/?task_id=<task_id>&submission_id=<submission_id>`
   - если комментарий из тренажёра (нет assignment): на `/student/history/?submission_id=<submission_id>`
3) При переходе **автоматически раскрывать блок “Вопросы/ответы”** у нужного задания и проскроллить к нему.
4) Поддержать deep-link в журнале ученика с учётом пагинации (если `submission_id` на другой странице — сервер редиректит на корректную `page`).

## Non-goals
- Новая отдельная страница “все комментарии” (пока достаточно блока + ссылки в журнал).
- Реалтайм-обновление без перезагрузки.
- Фильтры по предметам/вариантам в блоке (можно позже).

---

## UX / UI

### 1) Student dashboard (`core/student_dashboard.html`)
Новый блок “Комментарии” (ниже “Последние решения” либо рядом — по текущей сетке):
- Заголовок: “Комментарии”
- Справа: `20 из N` + ссылка “Все” (ведёт в `/student/history/`)
- Элемент списка:
  - бейдж `новое`, если `author_role="tutor"` и `seen_by_student_at is null`
  - чипы: “Репетитор/Вы”, “Вариант <title>” (если есть), “№<task_type.number>” (если есть)
  - превью текста (1–2 строки, обрезка)
  - дата/время
  - кликабелен целиком

### 2) Переходы
**A. Комментарий из варианта (есть `assignment_id`)**
URL:
`/student/assignment/<assignment_id>/?task_id=<task_id>&submission_id=<submission_id>`

Ожидаемое поведение:
- страница открывается
- прокрутка до карточки задачи
- автоматически раскрывается блок вопросов (чат) по задаче
- внутри чата не обязательно скроллить к конкретному сообщению (можно позже), достаточно открыть ветку

**B. Комментарий из тренажёра (assignment_id is null)**
URL:
`/student/history/?submission_id=<submission_id>`

Ожидаемое поведение:
- если submission на другой странице пагинации — сервер редиректит на нужный `page`
- на странице:
  - раскрываем блок `comments_sub_<id>`
  - скроллим к нему
  - подсвечиваем кратко (ring)

---

## Backend changes

### A) `core/views.py::student_dashboard`
Добавить выборку комментариев:
- `dashboard_comments`: последние 20 `SubmissionComment` по ученику, сортировка `-created_at`
- `dashboard_comments_total`: общее количество комментариев
- Для каждого комментария добавить поле `is_unread_for_student = (author_role == "tutor" and seen_by_student_at is None)`

Оптимизация:
- `.select_related("author", "submission", "submission__assignment", "submission__task", "submission__task__task_type")`

### B) `core/views.py::student_history`
Добавить поддержку deep-link `submission_id`:
- если передан `submission_id`:
  - находим `Submission(id=submission_id, student=request.user)`
  - вычисляем индекс в упорядоченном списке submissions (`order_by("-created_at")`)
  - вычисляем страницу по `per_page=20` (используем тот же лимит)
  - если `page` не совпадает — редиректим на `?page=<n>&submission_id=<id>`

Также в контекст передать `submission_id` (для шаблона/JS).

---

## Template / JS changes

### A) `core/templates/core/student_dashboard.html`
Добавить блок “Комментарии” и ссылки:
- if `c.submission.assignment_id`: строим URL на `student_solve_assignment` + query `task_id` и `submission_id`
- else: URL на `student_history` + query `submission_id`

### B) `core/templates/core/student_solve_assignment.html`
Добавить JS на `DOMContentLoaded`:
- читать `task_id` и `submission_id` из query params
- если `task_id` есть:
  - найти `.task-card[data-task-id="<task_id>"]`
  - `scrollIntoView({behavior:'smooth', block:'start'})`
  - если `submission_id` есть:
    - раскрыть чат: вызвать существующую `toggleTaskChat(task_id)` (если есть) или напрямую убрать `hidden` у `#chat_body_<task_id>`
    - дополнительно подсветить `#chat_block_<task_id>` или `#chat_body_<task_id>` (ring на 2.5 сек)

### C) `core/templates/core/student_history.html`
Добавить JS deep-link:
- читать `submission_id` из query
- найти `#comments_sub_<id>`
  - раскрыть его (убрать `hidden`)
  - `scrollIntoView`
  - подсветить

---

## Testing
Добавить тесты:
1) `student_dashboard` возвращает в контексте `dashboard_comments` и в HTML присутствуют тексты комментариев.
2) `student_history` с `?submission_id=<id>` редиректит на корректную страницу при нужде.
3) `student_solve_assignment` содержит нужные `data-task-id` и элементы `chat_body_<task_id>` (JS поведение можно ограничить smoke-проверкой наличия id-шников).

