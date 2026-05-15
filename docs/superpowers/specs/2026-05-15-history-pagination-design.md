# Pagination for Student & Tutor History (Journal) — Design

## Context
Сейчас “журнал решений” грузит весь объём данных:
- `student_history` (ученик): список `Submission` без пагинации.
- `tutor_student_history` (репетитор): загружает все `Submission`, потом группирует по дням (`history_days`) и раскрывает нужное решение по `?submission_id=<id>`.

Это приводит к тяжёлым страницам и проблемам UX при большом объёме истории.

## Goal
Добавить пагинацию:
1) **Ученик**: пагинация по решениям (`Submission`) — **20 на страницу**.
2) **Репетитор**: пагинация **по дням** (сохраняем текущую группировку по датам) — **14 дней на страницу**.
3) Сохранить deep-link сценарий: `?submission_id=<id>` должен **открывать нужный день и задачу** (как сейчас), даже если цель находится на другой странице пагинации.

## Non-goals
- Бесконечная прокрутка / “Показать ещё”.
- Фильтры (ошибки/предмет/тип) — можно добавить позже, но не в этой задаче.

---

## UX / UI requirements

### Student: `core/student_history.html`
- Внизу списка показать простой пагинатор:
  - “Назад”, “Вперёд”
  - “Страница N из M”
- URL параметр: `?page=<n>` (1-indexed).
- Отображаем **только submissions текущей страницы**, чтобы не рендерить тяжёлые HTML-условия/решения на тысячи записей.

### Tutor: `core/tutor_student_history.html`
- Пагинация по дням:
  - “Назад”, “Вперёд”
  - “Страница N из M”
- URL параметр: `?page=<n>`.
- `history_days` содержит **только 14 дней** текущей страницы.

### Deep-link behavior (tutor)
- Если запрос содержит `submission_id=<id>`:
  - Сервер определяет дату нужного submission (локальная дата) и вычисляет номер страницы, на которой лежит этот день.
  - Если `page` в URL отсутствует или не совпадает — делаем redirect на корректный URL:
    - `/tutor/student/<student_id>/history/?page=<correct>&submission_id=<id>`
  - После этого текущий JS (уже есть) раскрывает нужный день + `task_<id>` / `prac_task_<id>` и скроллит.

---

## Backend changes

### Student history pagination
Файл: `core/views.py::student_history`
- Заменить “все submissions” на `Paginator`:
  - `page = int(request.GET.get("page", "1"))`
  - `per_page = 20`
  - `page_obj = Paginator(qs, per_page).get_page(page)`
- В контекст:
  - `submissions = page_obj.object_list`
  - `page_obj`

Также важно:
- `_mark_student_replies_seen` — применять к `page_obj.object_list` (а не ко всем записям).

### Tutor history pagination by days
Файл: `core/views.py::tutor_student_history`
Текущее поведение:
- Берём `submissions = Submission.objects.filter(student=student).order_by("-created_at")`
- Группируем по локальной дате.

Новая схема:
1) Построить множество доступных дней (локальная дата) через `created_at`:
   - получить список дат (distinct) в порядке убывания.
2) Применить `Paginator` к списку дат:
   - `per_page_days = 14`
   - `page_obj_days`
3) Загрузить submissions **только** для дат текущей страницы (и только этого ученика).
4) Сгруппировать их в `history_days` как сейчас.

Deep-link:
- Если задан `submission_id`:
  - найти `Submission(id=submission_id, student=student)`
  - вычислить `target_day = localtime(created_at).date()`
  - найти индекс дня среди всех дней (позиция в отсортированном списке) → вычислить `target_page`
  - редиректить на `?page=target_page&submission_id=submission_id`, если нужно.

---

## Template changes

### `core/student_history.html`
- Добавить блок пагинации внизу (под списком):
  - Использовать `page_obj.has_previous`, `page_obj.previous_page_number`, `page_obj.has_next`, `page_obj.next_page_number`, `page_obj.number`, `page_obj.paginator.num_pages`.

### `core/tutor_student_history.html`
- Добавить блок пагинации внизу списка дней:
  - Аналогично, но на `page_obj_days` (название в контексте можно выбрать `page_obj` для единообразия).
- При построении URL важно сохранять `submission_id` (если он есть), чтобы после переключения страниц можно было всё равно подсветить цель.

---

## Edge cases
- Некорректный `page` (не число / <1 / >max): возвращаем ближайшее валидное (поведение `get_page`).
- `submission_id` не принадлежит ученику / не существует: игнорируем, без редиректа.
- Если у репетитора роль `tutor`: показываем только submissions, относящиеся к его вариантам, если это требование уже действует (не ломаем текущую политику доступа).

---

## Testing requirements
Добавить тесты:
1) Student history:
   - создаём 25 submissions → на первой странице 20, на второй 5.
2) Tutor history:
   - создаём submissions в 20 разных дат → на первой странице 14 дат.
3) Tutor deep-link:
   - `?submission_id=<id>` без `page` → 302 редирект на корректную страницу.

