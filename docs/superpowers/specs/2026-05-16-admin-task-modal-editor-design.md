# Platform-admin: модалка просмотра/редактирования задачи + Fix LaTeX

## Контекст и цель
Нужно добавить в **platform-admin** возможность:
1) выбрать задачу (по ID и через поиск/таблицу);
2) открыть её в модалке с **условием**, **решением** и **всеми изображениями**;
3) запустить для неё “улучшение конвертации LaTeX” (точечно по `task_id`, то есть перегенерить/нормализовать HTML);
4) вручную отредактировать условие/решение/ответ;
5) загрузить картинку и **автоматически вставить** её в HTML.

Пользователь уточнил:
- место: **platform-admin**
- “Fix LaTeX”: **перегенерить HTML для выбранной задачи**
- редактирование: **тексты + картинки**
- редактируемая тема: **только `classic`**

## Вне скоупа (чётко)
- Редактирование других тем (`dota/cs2/ussr`) в этой итерации
- Массовые операции “по типу” (это уже есть в другом месте и не требуется сейчас)
- Изменение логики проверки ответа ученика (меняем только данные задачи/HTML)

---

## UX / UI

### 1) Новый пункт меню platform-admin: «Задачи»
В левом меню админки добавить пункт, ведущий на новый экран:
- `GET /platform-admin/tasks/` → страница поиска задач.

### 2) Экран «Задачи»
Состоит из двух частей:
1) **Быстрый ввод ID**
   - input `Task ID`
   - кнопка «Открыть»
   - при нажатии открывает модалку задачи.

2) **Поиск + таблица**
   - строка поиска (q)
   - таблица результатов (id, fipi_id, тип, тема/предмет, превью первых N символов)
   - клик по строке открывает модалку задачи.

### 3) Модалка задачи
Модалка двухколоночная:

**Слева: “Просмотр”**
- Отрендеренный HTML условия
- Отрендеренный HTML решения
- Изображения показываются как `<img src="/media/...">` или внешние ссылки — как в HTML.

**Справа: “Редактор”**
- Поле `correct_answer`
- `content_html` (textarea)
- `solution_html` (textarea)
- Кнопки:
  - **Fix LaTeX (по задаче)** — запускает нормализацию и обновляет превью/textarea
  - **Сохранить** — сохраняет изменения
  - **Загрузить картинку в условие** — upload, затем вставляет `<img src="...">` в место курсора `content_html`
  - **Загрузить картинку в решение** — аналогично для `solution_html`

**Правила отображения/статусов**
- После открытия модалки сразу грузим JSON по `task_id`
- Все операции показывают статус (loading/success/error) в модалке, без перезагрузки страницы.

---

## Данные и хранение

### Какие модели используются
- `Task` — `correct_answer`, `fipi_id`, `task_type`, `topic`
- `TaskVariant` — `content`, `solution` для `theme="classic"`

**Важно:** отдельного ImageField для картинок задач нет; картинки — это `<img>` внутри HTML. Поэтому “редактирование картинок” = загрузить новый файл в media и вставить его в HTML.

---

## API / эндпоинты

### 1) Получить данные задачи
`GET /platform-admin/tasks/<task_id>/json/`

Ответ:
```json
{
  "task": {
    "id": 123,
    "fipi_id": "....",
    "correct_answer": "0.175",
    "exam_format": "ЕГЭ 2026",
    "task_type_number": 1,
    "task_type_name": "...",
    "topic_name": "..."
  },
  "variant": {
    "theme": "classic",
    "content_html": "<p>...</p>",
    "solution_html": "<p>...</p>"
  }
}
```

### 2) Сохранить правки
`POST /platform-admin/tasks/<task_id>/update/`
Body (JSON):
```json
{
  "correct_answer": "...",
  "content_html": "...",
  "solution_html": "..."
}
```
Сохраняет:
- `Task.correct_answer`
- `TaskVariant(theme="classic").content/solution` (create if missing)

### 3) Fix LaTeX (по задаче)
`POST /platform-admin/tasks/<task_id>/fix-latex/`

Поведение:
- Берёт `TaskVariant(theme="classic")`
- Прогоняет `content` и `solution` через pipeline:
  1) `replace_svg_images_with_latex`
  2) `fix_latex_tokens_in_html`
  3) `normalize_task_html`
  4) `fix_math_words_in_html`
- Сохраняет результат в `TaskVariant`
- Возвращает обновлённые поля (как в `.../json/`)

### 4) Upload изображения (для вставки в HTML)
`POST /platform-admin/tasks/upload-image/`

Form-data:
- `file`
- `target` in `{content,solution}` (только для аналитики/имени файла)

Ответ:
```json
{ "url": "/media/tasks/admin_upload/<uuid>.png" }
```

---

## Безопасность и доступ
- Все endpoints доступны только пользователю с `role="admin"`.
- Upload: ограничение по типам файлов (png/jpg/webp/gif/svg) и размеру.

---

## Тестирование

1) Страница `/platform-admin/tasks/`:
- admin: 200
- non-admin: 403/redirect

2) JSON endpoint:
- отдаёт `correct_answer`, `content_html`, `solution_html`

3) Update endpoint:
- меняет `Task.correct_answer`
- меняет `TaskVariant.content/solution`

4) Fix-latex endpoint:
- на контролируемом входе меняет HTML (минимальный тест на `replaced_count > 0` или на наличие `$...$`)

5) Upload endpoint:
- возвращает `/media/...`
- файл реально сохраняется через `default_storage` (проверка exists)

