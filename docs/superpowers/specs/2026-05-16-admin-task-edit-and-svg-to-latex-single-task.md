# Дизайн: редактирование задачи в админке + SVG→LaTeX для одной задачи (classic)

Дата: 2026-05-16

## Цель

Сделать в Django admin удобный поток для контент‑правок:
1) редактировать **отдельную задачу** (условие и решение);
2) запускать для неё **конвертацию SVG→LaTeX** (для улучшения рендеринга формул) с **предпросмотром (dry-run)**;
3) при этом **НЕ менять `Task.correct_answer` автоматически**.

## Контекст: где хранятся данные

- `Task` — сущность задания (тип, тема, ручная сложность и т.п.).
- Текст/HTML хранятся в `TaskVariant`:
  - `TaskVariant.theme` (например `classic`)
  - `TaskVariant.content` (условие, HTML)
  - `TaskVariant.solution` (решение, HTML)

Улучшение рендеринга LaTeX делается в двух направлениях:
- “мягкие” фиксы на лету в `Task.get_content_for_theme()`/`get_solution_for_theme()` через `core/tex_replace.py`;
- “жёсткая” правка данных в БД: конвертация SVG формул в `$...$` (есть сервис `core/services_svg_to_latex.py` и команда `convert_oge_type6_svg_to_latex.py` для массовой конвертации).

## Требования

### R1. Редактирование условия/решения в админке

- На странице Django admin для `Task` должно быть удобно редактировать:
  - `TaskVariant(theme=classic).content`
  - `TaskVariant(theme=classic).solution`
- Предпочтение: inline‑редактор на странице `Task` (TabularInline/StackedInline).

### R2. Конвертация SVG→LaTeX “по одной задаче”

- На странице редактирования `Task` должна быть кнопка **«SVG→LaTeX (classic)»**.
- При нажатии сначала открывается **предпросмотр**:
  - статистика (сканировано/изменено/сколько замен);
  - предпросмотр “до/после” (хотя бы для `content` и `solution`).
- Только после явного подтверждения “Применить” изменения записываются в БД.

### R3. Scope конвертации

- Конвертируем только `theme=classic`.
- Конвертируем `TaskVariant.content` и `TaskVariant.solution`.
- После конвертации дополнительно прогоняем HTML через фиксы из `core/tex_replace.py` и сохраняем результат, чтобы рендер был стабильным.
- `Task.correct_answer` **не изменяем** автоматически.

### R4. Права доступа

- Доступ только пользователям admin (staff) по стандартным правилам Django admin.

## UX/Flow

1) Admin → `Task` → открывает задачу.
2) В инлайне видит и правит `classic`‑вариант (условие/решение).
3) Нажимает кнопку **«SVG→LaTeX (classic)»**.
4) Переходит на страницу предпросмотра:
   - показывает статистику;
   - показывает блоки “до/после” (content и solution отдельно).
5) Нажимает **«Применить»** → изменения сохраняются, показывается `messages.success`, переход обратно в `Task` change‑form.

## Техническая реализация (высокоуровнево)

### 1) Admin inline для `TaskVariant`

- Добавить `TaskVariantInline` к `TaskAdmin`.
- Ограничить отображение/редактирование `theme=classic`:
  - либо показывать все, но валидацией/подсказкой выделять classic;
  - либо ограничить queryset инлайна только classic (предпочтительно).

### 2) Кнопка на странице `Task` и отдельный URL

- В `TaskAdmin` добавить кастомный URL через `get_urls()`:
  - `/admin/core/task/<id>/svg-to-latex-preview/` (GET: предпросмотр)
  - `/admin/core/task/<id>/svg-to-latex-apply/` (POST: применить)
- В change-form добавить кнопку, ведущую на preview URL (через `change_form_template` или `ModelAdmin.change_view` + extra_context).

### 3) Сервис “конвертация для одной задачи”

- Вынести/добавить функцию уровня сервиса, работающую с одной задачей:
  - вход: `task_id`, `theme='classic'`, `dry_run=True/False`
  - выход: структура со статистикой и новым HTML (content/solution).
- Реиспользовать существующие функции из `core/services_svg_to_latex.py` по максимуму.

### 4) Фиксы LaTeX/слов в HTML (жёстко, с сохранением)

- После SVG→LaTeX прогнать:
  - `fix_latex_tokens_in_html()`
  - `fix_math_words_in_html()`
- Сохранить отфиксенный HTML обратно в `TaskVariant`.

## Тестирование

- Юнит/интеграционные тесты на:
  - появление inline (минимально: модель зарегистрирована/форма доступна);
  - preview endpoint: dry-run не меняет БД;
  - apply endpoint: меняет `TaskVariant.content/solution` и не трогает `Task.correct_answer`.

## Критерии готовности

- В Django admin можно открыть `Task`, отредактировать `classic` content/solution.
- Можно запустить SVG→LaTeX для одной задачи:
  - сначала preview,
  - затем apply,
  - после apply формулы отображаются как LaTeX, а не SVG.
- `Task.correct_answer` не меняется.

