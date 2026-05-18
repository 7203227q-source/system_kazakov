# Live-предпросмотр в редакторе задачи (банк заданий)

## Контекст

Сейчас у админа в «База заданий» есть кнопка **«Редактировать»** (рядом с **«ИИ: Регенерировать»**), которая ведёт на страницу `/tutor/tasks/<id>/edit/` с двумя textarea:
- `TaskVariant(theme="classic").content`
- `TaskVariant(theme="classic").solution`

Проблема: на странице редактирования видно «сырой HTML» (условие/решение), но **не видно итоговый рендер**, как он будет выглядеть в интерфейсе (MathJax, картинки, реальная вёрстка). Также важно, чтобы **картинки подгружались и отображались** прямо в редакторе.

## Цели

1. Добавить на страницу редактирования задачи **live-предпросмотр** (обновляется во время набора).
2. Предпросмотр должен показывать:
   - как выглядит **условие**
   - как выглядит **решение**
   - как выглядит **ответ** (у нас это `Task.correct_answer`)
3. В предпросмотре должны отображаться **картинки** (включая те, которые идут через `/proxy-image/?url=...`), и кликом по картинке должно открываться увеличение (лайтбокс), как в других страницах.
4. Предпросмотр должен максимально соответствовать «как в проде»:
   - прогон HTML через `fix_latex_tokens_in_html`, `fix_math_words_in_html`, `normalize_task_html`
   - рендер формул через MathJax

## Не-цели

- Не делаем WYSIWYG-редактор (Quill/TinyMCE и т.п.) — остаются textarea.
- Не меняем логику сохранения `correct_answer`.
- Не делаем доступ для tutor (остаётся admin-only, как согласовано ранее).

## UX / UI дизайн

### Макет страницы

Страница `core/templates/core/task_edit.html` станет двухколоночной (на desktop):
- **Слева**: textarea для `content` и `solution` (как сейчас).
- **Справа**: блок «Предпросмотр», который содержит:
  - «Ответ: …» (берём `task.correct_answer`)
  - «Условие (preview)» — `div.prose` с HTML
  - «Решение (preview)» — `div.prose` с HTML (если пусто, показываем заглушку «Нет решения»)

На mobile можно показывать колонки вертикально (сначала редактор, затем предпросмотр) — достаточно responsive grid (Tailwind).

### Поведение live

- При вводе в textarea срабатывает **debounce** (например, 700мс).
- После debounce отправляется запрос на endpoint «render preview» и обновляет блоки предпросмотра.
- После обновления HTML:
  - вызывается `MathJax.typesetPromise()` (если MathJax доступен)
  - заново навешиваются обработчики лайтбокса на `<img>` внутри предпросмотра

### Картинки

Мы не меняем `src` на странице редактирования — просто рендерим HTML, а браузер сам подгружает картинки.

Важно:
- В проекте уже есть `/proxy-image/?url=...` (используется для доменов sdamgia.ru), это должно продолжать работать.
- Для увеличения используем существующий partial `core/templates/core/image_modal.html`.

## Backend дизайн

### Новый endpoint для предпросмотра

Добавляем admin-only endpoint:

`POST /tutor/tasks/<task_id>/render-preview/`

Вход:
- `content` (string)
- `solution` (string)

Выход (JSON):
- `content_html` — отфиксенный HTML для предпросмотра
- `solution_html` — отфиксенный HTML для предпросмотра

Обработка:
1. `fix_latex_tokens_in_html(html)` → `(html, changed)`
2. `fix_math_words_in_html(html)` → `(html, changed)`
3. `normalize_task_html(html)` → `html`

Примечание: мы делаем это **без сохранения в БД** (чистый preview).

### Права доступа

Все новые маршруты и view для редактора/preview остаются **admin-only**:
- если не admin — redirect на `tutor_task_bank` (как сейчас).

## Реализация фронта

### Подключение MathJax

Скопировать конфигурацию MathJax из `core/templates/core/tutor_task_bank.html` (там уже используется MathJax v3).

### JS для live preview

Добавить JS:
- функция `debounce(fn, ms)`
- функция `renderPreview()`:
  - читает `textarea[name=content]` и `textarea[name=solution]`
  - делает `fetch()` на `/tutor/tasks/<id>/render-preview/` с CSRF
  - обновляет DOM блоков предпросмотра
  - вызывает `MathJax.typesetPromise()` и `bindPreviewImages()`
- на `input` обоих textarea — вызывать `debouncedRenderPreview()`
- `bindPreviewImages()` — аналогично коду из `image_modal.html`, но вызывается и на старте, и после каждого обновления preview

## Тестирование

Добавить тесты:

1. **Endpoint smoke test**:
   - логиним admin
   - POST на `render-preview` с HTML, содержащим `<img src="/formula/svg/1.svg" ...>` и фрагментом latex-токенов
   - ожидаем 200 и наличие `content_html`/`solution_html` в JSON

2. **Permission test**:
   - логиним tutor
   - POST на endpoint → должен быть 302 (редирект) или 403 (если решим так), но консистентно с текущим подходом (скорее 302).

UI e2e тесты не добавляем (дорого), достаточно backend smoke + существующих unit тестов на SVG→LaTeX.

## Риски и ограничения

- Live preview с MathJax может быть тяжёлым на больших задачах, поэтому делаем debounce (700мс) и показываем небольшой индикатор «Обновление…».
- Если HTML содержит внешние картинки, загрузка может быть медленной — это ок, т.к. это именно предпросмотр.

