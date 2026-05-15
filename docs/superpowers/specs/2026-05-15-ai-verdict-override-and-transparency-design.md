# AI verdict visibility + Tutor override in journal — Design

## Context / Problems
1) Репетитор должен иметь возможность **исправить оценку ИИ** как:
   - в просмотре варианта (`tutor_assignment_view`)
   - так и в журнале решений ученика у репетитора (`tutor_student_history`)
2) Ученик в варианте сейчас видит вердикт ИИ **не полностью** (в основном `ai_feedback`), тогда как у репетитора доступен более полный блок (распознанное решение / ошибки / вердикт).
3) ИИ иногда **додумывает** решение ученика: вместо строгого следования фото строит своё решение и подгоняет оценку.

## Goals
1) Добавить UI для **override оценки** в журнале репетитора (и унифицировать логику сохранения).
2) Сделать в варианте ученика отображение **полного отчёта ИИ** (recognized_solution + mistakes + verdict + фото), как у репетитора.
3) Отрегулировать prompt проверки по фото в режиме **«Мягко»**:
   - ИИ может оценивать,
   - но обязан явно отмечать места неуверенности/нечитаемости
   - и не имеет права «додумывать» шаги решения без пометки.

## Non-goals
- Полноценный OCR с построчной разметкой и координатами.
- Модель “confidence score” в базе и отдельная ML-логика (пока достаточно текстовых правил).
- Переработка всей системы проверки (только улучшения prompt + UI).

---

## Feature A: Tutor override score in tutor journal

### UX
В `core/templates/core/tutor_student_history.html` рядом с каждой задачей (submission) показываем:
- текущую оценку (эффективную): если есть `tutor_primary_score` — показываем её и пометку “исправлено репетитором”, иначе `primary_score`
- мини-форму:
  - input: “Баллы репетитора” (0..max_points)
  - кнопка “Сохранить”

При сохранении:
- запрос на существующий endpoint `/api/tutor/submission/<id>/override-score/`
- после успеха обновляем UI (можно `location.reload()` как простой и надёжный вариант)

### Backend
Endpoint `api_tutor_override_score` уже существует и уже обновляет:
- `tutor_primary_score`, `tutor_scored_at`
- и также итоговые `primary_score`, `score`, `is_correct` (чтобы пересчёты и видимость работали везде)

Задача здесь — только подключить этот endpoint к журналу репетитора.

---

## Feature B: Student sees full AI report in assignment

### UX
В `core/templates/core/student_solve_assignment.html` для задач, где есть любое из полей:
- `image_url` / `image_url_2`
- `ai_recognized_solution`
- `ai_mistakes_json`
- `ai_verdict_json`
- `ai_feedback`

добавляем раскрывающийся блок “Фото и вердикт ИИ”, содержимое:
1) Фото решения (1-я и 2-я страница, если есть)
2) “Решение (как распознано)” — `ai_recognized_solution` (pre-wrap)
3) “Ошибки и замечания” — `ai_mistakes`
4) “Итоговый вердикт” — `ai_verdict` (абзацы)
5) “Коротко” — `ai_feedback_display_html` (если есть)

### Data prep
В `student_solve_assignment` view нужно так же, как в `tutor_student_history`, распарсить:
- `ai_mistakes_json` → `ai_mistakes` list
- `ai_verdict_json` → `ai_verdict` list
- `ai_feedback` → `ai_feedback_display_html` (уже делается в части кода; важно убедиться, что это работает и для варианта ученика)

---

## Feature C: Prompt tuning (soft anti-hallucination)

### Current behavior
В `verifyWithAI` prompt просит `recognized_solution` “как ты понял ход решения ученика”, но не запрещает домыслы явно.

### New prompt rules (“Мягко”)
Добавляем требования в prompt:
- `recognized_solution`:
  - описывай **только то, что реально видно** на фото (что написано/какие преобразования)
  - если часть не читается/не видна — явно вставляй маркеры вида: `[неразборчиво]`, `[не видно]`, `[сомнение]`
  - не добавляй шаги, которых нет на фото, без пометки “предположил(а)”
- `verdict` должен включать отдельный абзац:
  - “Где распознавание сомнительно/не удалось прочитать”
  - “Как это могло повлиять на оценку”
- Разрешаем оценку, но запрещаем уверенные утверждения без основания.

### Acceptance criteria (qualitative)
После изменения prompt:
- recognized_solution становится ближе к “пересказу видимого”
- вердикт явно сообщает о неуверенности
- меньше случаев, когда ИИ “решает сам” без связи с фото

---

## Testing
1) Добавить тест на отображение блока ИИ у ученика в варианте (smoke):
   - создать submission с заполненными `ai_recognized_solution` + `ai_mistakes_json` + `ai_verdict_json`
   - убедиться, что HTML содержит эти фрагменты
2) Добавить тест/проверку на наличие UI override в `tutor_student_history` (smoke):
   - проверить, что на странице есть input/кнопка для сохранения (можно по тексту/атрибутам)

