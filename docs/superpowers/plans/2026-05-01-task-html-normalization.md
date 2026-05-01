# Task HTML Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать «столбик» в условии/решении задач, нормализуя «сломанный» HTML (частые `<br>`), и применить это как для новых импортов, так и разово для уже загруженной базы.

**Architecture:** Ввести чистую утилиту `normalize_task_html(html)` (BeautifulSoup) и использовать её (1) в импорте из CSV и (2) в management-команде для пакетной нормализации существующих `TaskVariant`.

**Tech Stack:** Django, BeautifulSoup4, Django management commands, Django tests (`SimpleTestCase`).

---

## Затрагиваемые файлы

- Create: `/workspace/core/task_html.py`
- Create: `/workspace/core/management/commands/normalize_task_html.py`
- Modify: `/workspace/core/services_csv.py`
- Create: `/workspace/core/tests/test_task_html_normalization.py`

---

### Task 1: Добавить тесты для normalize_task_html

**Files:**
- Create: `/workspace/core/tests/test_task_html_normalization.py`

- [ ] **Step 1: Write the failing test**

```python
from django.test import SimpleTestCase


class NormalizeTaskHtmlTests(SimpleTestCase):
    def test_leaves_small_number_of_br_intact(self):
        from core.task_html import normalize_task_html

        html = "<p>а) Докажите, что ...<br>б) Найдите ...</p>"
        self.assertEqual(normalize_task_html(html), html)

    def test_collapses_many_br_into_spaces_in_plain_paragraph(self):
        from core.task_html import normalize_task_html

        html = "<p>Высоты<br>BB₁<br>и<br>CC₁<br>остроугольного<br>треугольника<br>ABC<br>пересекаются<br>в точке<br>H.</p>"
        out = normalize_task_html(html)
        self.assertIn("Высоты BB₁ и CC₁ остроугольного треугольника ABC пересекаются в точке H.", out)
        self.assertNotIn("<br", out)

    def test_does_not_touch_lists_and_tables(self):
        from core.task_html import normalize_task_html

        html = "<ul><li>А</li><li>Б</li></ul><table><tr><td>1</td></tr></table>"
        self.assertEqual(normalize_task_html(html), html)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest -q core/tests/test_task_html_normalization.py
```

Expected: FAIL (module `core.task_html` / function missing).

---

### Task 2: Реализовать normalize_task_html

**Files:**
- Create: `/workspace/core/task_html.py`
- Modify: `/workspace/core/tests/test_task_html_normalization.py` (если понадобится подогнать ожидаемое значение)

- [ ] **Step 1: Write minimal implementation**

```python
import re

from bs4 import BeautifulSoup


DEFAULT_BR_THRESHOLD = 8


def normalize_task_html(html: str, *, br_threshold: int = DEFAULT_BR_THRESHOLD) -> str:
    if not html:
        return html

    soup = BeautifulSoup(html, "html.parser")

    for block in soup.find_all(["p", "div", "span"]):
        if block.find(["ul", "ol", "li", "table", "tr", "td", "th", "pre", "code"]):
            continue

        brs = block.find_all("br")
        if len(brs) < br_threshold:
            continue

        for br in brs:
            br.replace_with(" ")

        normalized_text = re.sub(r"[ \t\r\n]+", " ", block.get_text(separator=" ", strip=True))
        block.clear()
        block.append(normalized_text)

    return str(soup)
```

- [ ] **Step 2: Run tests**

Run:

```bash
pytest -q core/tests/test_task_html_normalization.py
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add core/task_html.py core/tests/test_task_html_normalization.py
git commit -m "fix: normalize broken task HTML (br collapse)"
```

---

### Task 3: Подключить нормализацию в CSV-импорт

**Files:**
- Modify: `/workspace/core/services_csv.py`
- Test: `/workspace/core/tests/test_task_html_normalization.py` (опционально добавить ещё кейс)

- [ ] **Step 1: Update import pipeline**

Изменить импорт в `services_csv.py`:

```python
from .task_html import normalize_task_html
```

И применить перед сохранением:

```python
processed_content = download_and_replace_images(content, fipi_id, theme)
processed_solution = download_and_replace_images(solution, fipi_id, theme)

processed_content = normalize_task_html(processed_content)
processed_solution = normalize_task_html(processed_solution)
```

- [ ] **Step 2: Run unit tests**

Run:

```bash
pytest -q core/tests/test_task_html_normalization.py
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add core/services_csv.py
git commit -m "fix: normalize task HTML during CSV import"
```

---

### Task 4: Добавить management-команду для разовой нормализации существующих задач

**Files:**
- Create: `/workspace/core/management/commands/normalize_task_html.py`

- [ ] **Step 1: Implement command**

```python
from django.core.management.base import BaseCommand

from core.models import TaskVariant
from core.task_html import normalize_task_html


class Command(BaseCommand):
    help = "Normalize TaskVariant.content/solution HTML by collapsing excessive <br> into spaces"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--theme", type=str, default="")
        parser.add_argument("--br-threshold", type=int, default=8)

    def handle(self, *args, **options):
        limit = options["limit"]
        dry_run = options["dry_run"]
        theme = options["theme"].strip()
        br_threshold = options["br_threshold"]

        qs = TaskVariant.objects.all().order_by("id")
        if theme:
            qs = qs.filter(theme=theme)
        if limit:
            qs = qs[:limit]

        changed = 0
        scanned = 0

        for v in qs.iterator(chunk_size=200):
            scanned += 1

            new_content = normalize_task_html(v.content, br_threshold=br_threshold)
            new_solution = normalize_task_html(v.solution, br_threshold=br_threshold) if v.solution else v.solution

            if new_content != v.content or new_solution != v.solution:
                changed += 1
                if not dry_run:
                    v.content = new_content
                    v.solution = new_solution
                    v.save(update_fields=["content", "solution"])

        mode = "DRY-RUN" if dry_run else "APPLIED"
        self.stdout.write(self.style.SUCCESS(f"{mode}: scanned={scanned}, changed={changed}"))
```

- [ ] **Step 2: Smoke-check command imports**

Run:

```bash
python manage.py help normalize_task_html
```

Expected: help output without stacktrace.

- [ ] **Step 3: Commit**

```bash
git add core/management/commands/normalize_task_html.py
git commit -m "chore: add command to normalize existing task HTML"
```

---

### Task 5: Прогон на проде (операционная инструкция)

**Files:** none

- [ ] **Step 1: Dry-run на небольшой выборке**

Run on server:

```bash
python manage.py normalize_task_html --limit 200 --dry-run
```

Expected: `DRY-RUN: scanned=200, changed=<N>`

- [ ] **Step 2: Реальный запуск батчами**

Run on server:

```bash
python manage.py normalize_task_html --limit 1000
```

Repeat until `changed` becomes small.

- [ ] **Step 3: Проверка в UI**

Открыть `/tutor/tasks/` и проверить несколько проблемных задач: больше нет «столбика», пункты «а) / б)» не склеены.

---

## Self-review

- Spec coverage: план покрывает (1) нормализацию при импорте и (2) разовую чистку существующих данных, с `dry-run` и порогом.
- Placeholder scan: нет `TODO/TBD`, каждая задача содержит конкретный код и команды.
- Type consistency: используется единая функция `normalize_task_html` и один порог `--br-threshold` (default 8).
