## Цель
Добавить для администратора в “Базе заданий” (страница `/tutor/tasks/`) возможность регенерировать (уникализировать) отдельную задачу через OpenRouter API, с окном “шаблона промпта”, предпросмотром результата и сохранением в базе.

## Область работ (MVP)
- Расширить страницу банка заданий для роли `admin`:
  - фильтрация “сверху вниз”: `Subject -> ExamFormat -> TaskType -> subtype_tag`
  - у каждой карточки задачи: кнопка “ИИ: Регенерировать”
  - модальное окно с:
    - исходными данными (условие/решение/ответ + метаданные)
    - шаблонным промптом (редактируемый textarea)
    - выбором режима регенерации (по умолчанию: условие + ответ + решение)
    - выбором модели OpenRouter (строка; позже можно заменить на select)
    - кнопками: “Предпросмотр” (не сохраняет) и “Применить и сохранить”
- Серверная часть:
  - эндпоинт предпросмотра регенерации (POST, admin-only)
  - эндпоинт сохранения регенерации (POST, admin-only)
  - логирование каждой генерации в отдельную таблицу

## Пользовательский сценарий
1) Admin открывает `/tutor/tasks/`.
2) Выбирает предмет, формат, тип, подтип.
3) Открывает карточку задачи и нажимает “ИИ: Регенерировать”.
4) В модалке:
   - видит исходник задачи и текущий правильный ответ
   - видит шаблон промпта и может править
   - нажимает “Предпросмотр” → получает новый вариант (без записи в базу)
   - если устраивает, нажимает “Применить и сохранить” → запись в базу

## Данные и модели
Текущие модели:
- `Task`: `fipi_id`, `topic`, `task_type`, `subtype_tag`, `correct_answer`, `difficulty`, `exam_points`
- `TaskVariant`: `task`, `theme`, `content`, `solution`

Новая модель (MVP):
- `TaskGenerationLog`
  - `task` (FK)
  - `user` (FK -> User)
  - `provider` (строка, например `openrouter`)
  - `model` (строка)
  - `mode` (enum: `full`, `content_only`, `content_solution`)
  - `prompt_template` (text)
  - `prompt_rendered` (text)
  - `response_raw` (text/json)
  - `result_content_html` (text, nullable)
  - `result_solution_html` (text, nullable)
  - `result_correct_answer` (text, nullable)
  - `status` (enum: `success`, `error`)
  - `error_message` (text, nullable)
  - `created_at`

## Интеграция OpenRouter
Сделать сервис `openrouter_client.py` (или `services_openrouter.py`) который:
- читает `OPENROUTER_API_KEY` из env
- делает POST на OpenRouter (чат-комплишн) и просит строго JSON-ответ
- обрабатывает ошибки и таймауты

Формат результата от модели (строго JSON):
```json
{
  "content_html": "...",
  "solution_html": "...",
  "correct_answer": "...",
  "notes": "..."
}
```

## Сохранение результата
По умолчанию режим `full`:
- `TaskVariant(theme='classic').content` = `content_html`
- `TaskVariant(theme='classic').solution` = `solution_html`
- `Task.correct_answer` = `correct_answer`

Если варианта `classic` нет — создать.

## UI/UX
Изменения в [tutor_task_bank.html](file:///workspace/system_kazakov/core/templates/core/tutor_task_bank.html):
- добавить фильтры Subject/ExamFormat (только для admin, вверху над текущими фильтрами)
- добавить кнопку “ИИ: Регенерировать” на карточку задачи
- добавить модалку (Tailwind) с двумя колонками (исходник / настройки+предпросмотр)
- предпросмотр результата отображать справа (и хранить в JS-переменной до сохранения)

## Права доступа
Все действия регенерации доступны только роли `admin`.

## Обработка ошибок
- Если ключ OpenRouter отсутствует: показывать понятное сообщение (toast/alert).
- Если модель вернула невалидный JSON: показывать ошибку + сохранять raw response в лог.
- Таймаут: показывать “превышено время ожидания”.

## Тестирование
- Юнит-тест сервиса парсинга JSON-ответа
- Тесты на права доступа: non-admin получает 403/redirect
- “Сухой прогон” (dry-run) предпросмотра на одной задаче в dev
