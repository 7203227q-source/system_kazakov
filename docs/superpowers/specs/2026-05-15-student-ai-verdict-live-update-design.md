# Student assignment: live update AI verdict (no reload) — Design

## Problem
На странице варианта ученика после нажатия **«Проверить через ИИ»** вердикт/баллы иногда становятся видны только после ручного обновления страницы.

Причина: зелёный блок `ai-feedback-block` в `student_solve_assignment.html` отрисовывается сервером только если у `saved_submission` уже есть `ai_feedback`. После успешного `verifyWithAI()` мы показываем вердикт в `result_*`, но сам `ai-feedback-block` не “перерисовывается” без reload.

## Goal
Сделать так, чтобы после успешного ответа `/api/submission/<id>/verify/`:
- блок “Оценено / Вердикт ИИ” появлялся и обновлялся **сразу**, без `location.reload()`.

## Non-goals
- Реалтайм-подписки/вебсокеты.
- Перенос всей логики в отдельный фронтенд-фреймворк.

---

## Proposed solution (recommended)
1) В `student_solve_assignment.html` для задач с фото всегда иметь контейнер `ai-feedback-block` (изначально `hidden`).
2) В `verifyWithAI(submissionId, taskId)` после успешного ответа:
   - заполнить контейнер данными из ответа:
     - primary_score / is_correct
     - structured fields: recognized_solution / mistakes / verdict (если пришли)
     - fallback: feedback_html / feedback
   - снять `hidden` и (опционально) проскроллить к блоку.

## UI/UX
- Визуально используем уже существующий дизайн зелёного блока.
- Не трогаем `result_*` (оставляем как “оперативный” вывод), но делаем, чтобы и основной блок ниже фото становился актуальным.

---

## Implementation notes

### Template: `core/templates/core/student_solve_assignment.html`
- Добавить контейнер:
  - `div#ai_feedback_block_<taskId>` (hidden)
  - `div#ai_feedback_title_<taskId>` (заголовок “Оценено: …”)
  - `div#ai_feedback_body_<taskId>` (контент вердикта)
- Если на сервере уже есть `ai_feedback_display_html`, можно отрендерить внутрь `ai_feedback_body_...` как начальное значение.

### JS: `verifyWithAI(...)`
- После блока, где сейчас заполняется `resultDiv`, обновить `ai_feedback_*`:
  - `titleEl.innerHTML = ...`
  - `bodyEl.innerHTML = ...` (structured -> HTML, fallback -> feedback_html)
  - `blockEl.classList.remove('hidden')`

---

## Testing
- Smoke-тест: на странице варианта ученика присутствуют элементы `ai_feedback_block_<taskId>` для задач с `needs_photo=True` (или с saved_submission), даже если `ai_feedback` ещё пустой.
- Можно не делать JS-e2e тесты (достаточно наличия контейнера; логика JS уже используется в других местах).

