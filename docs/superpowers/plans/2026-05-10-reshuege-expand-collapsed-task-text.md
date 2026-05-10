# ReshuEGE “Развернуть” Import Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When importing OGE tasks (especially bundle 1–5), always store the full task statement (including the shared image/plan) even if the page uses a “Развернуть” collapsed block.

**Architecture:** Adjust HTML extraction in the SDAMGIA importer to prefer `div#text<task_id>` (the expanded statement) and only fall back to `div#body...` when `text<task_id>` is absent. Keep the rest of the pipeline unchanged (image download, solution extraction, bundle linking).

**Tech Stack:** Django, BeautifulSoup, existing `core.services_reshuege` importer, existing `download_and_replace_images`.

---

## File Map

**Modify**
- `core/services_reshuege.py` — make `parse_task_page` aware of `task_id` and extract the expanded statement node.

**Add / Modify tests**
- `core/tests/test_sdamgia_bundle_import.py` — keep existing bundle test intact.
- Create: `core/tests/test_sdamgia_expand_text_block_import.py` — add a focused regression test for “Развернуть”/`text<id>` statement extraction.

---

### Task 1: Make statement extraction prefer `text<id>`

**Files:**
- Modify: `core/services_reshuege.py`
- Test: `core/tests/test_sdamgia_expand_text_block_import.py`

- [ ] **Step 1: Write failing regression test**

Create `core/tests/test_sdamgia_expand_text_block_import.py`:

```python
from unittest.mock import patch

from django.test import TestCase

from core.models import ExamFormat, Subject, Task, TaskType, Topic
from core.services_reshuege import import_one_task_from_sdamgia


class SdamgiaExpandTextBlockImportTests(TestCase):
    def test_import_prefers_text_task_id_block_over_body(self):
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)

        html = '''
        <html><body>
          <div id="body999999"><p>Короткий текст без картинки</p></div>
          <div id="text408182">
            <p>Полный текст</p>
            <img src="/get_file?id=1">
          </div>
          <div id="sol408182"><p>Решение. Ответ: 213.</p></div>
          Ответ: 213.
        </body></html>
        '''

        with patch("core.services_reshuege.fetch_task_page_html", return_value=html), patch(
            "core.services_reshuege.download_and_replace_images", side_effect=lambda h, *_args, **_kwargs: h
        ):
            import_one_task_from_sdamgia(
                exam_format_id=exam_format.id,
                type_number=1,
                task_id="408182",
                base_url="https://math-oge.sdamgia.ru",
                skip_no_answer=False,
                skip_prototype=False,
                skip_no_solution=False,
                skip_existing=True,
                exclude_larin=False,
                theme="classic",
            )

        task = Task.objects.get(fipi_id="408182")
        v = task.variants.get(theme="classic")
        assert 'id="text408182"' in v.content
        assert "/get_file?id=1" in v.content
        assert "Короткий текст" not in v.content
```

- [ ] **Step 2: Run the new test to confirm it fails**

Run:
```bash
python manage.py test core.tests.test_sdamgia_expand_text_block_import -v 1
```

Expected: FAIL, because the importer currently selects `body...` instead of `text<id>`.

- [ ] **Step 3: Implement statement selection helper**

In `core/services_reshuege.py`, refactor `parse_task_page` to accept `task_id`:

```python
def parse_task_page(html: str, *, task_id: str | None = None) -> tuple[str, str, str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")

    statement_node = None
    if task_id:
        statement_node = soup.find("div", id=f"text{task_id}") or soup.find("div", id=f"body{task_id}")
    if statement_node is None:
        statement_node = soup.find("div", id=re.compile(r"^body\\d+$"))

    solution_node = None
    if task_id:
        solution_node = soup.find("div", id=f"sol{task_id}")
    if solution_node is None:
        solution_node = soup.find("div", id=re.compile(r"^sol\\d+$")) or soup.find(
            "div", class_=re.compile(r"\\bsolution\\b", flags=re.IGNORECASE)
        )

    content_node = statement_node or (
        soup.select_one("div.prob_maindiv")
        or soup.select_one("div.problem")
        or soup.select_one("div#problem")
        or soup.select_one("div.task")
        or soup.select_one("div#task")
    )

    content_html = str(content_node) if content_node else ""

    # (keep answer extraction and solution extraction logic unchanged)
    ...
```

- [ ] **Step 4: Wire the new signature into import flow**

In `import_one_task_from_sdamgia`, change:

```python
content_html, answer, solution_html = parse_task_page(html)
```

to:

```python
content_html, answer, solution_html = parse_task_page(html, task_id=task_id)
```

- [ ] **Step 5: Run the regression test again**

Run:
```bash
python manage.py test core.tests.test_sdamgia_expand_text_block_import -v 1
```

Expected: PASS.

- [ ] **Step 6: Run full test suite**

Run:
```bash
python manage.py test core.tests -v 1
```

Expected: PASS.

---

### Task 2: Verify bundle 1–5 import still works and includes image

**Files:**
- Modify: `core/tests/test_sdamgia_bundle_import.py` (only if needed)

- [ ] **Step 1: Run the existing bundle test**

Run:
```bash
python manage.py test core.tests.test_sdamgia_bundle_import -v 1
```

Expected: PASS.

- [ ] **Step 2: (Optional) Extend bundle test to assert expanded content**

If we want extra safety, extend the existing fixture HTML in `test_sdamgia_bundle_import.py` to include:

```html
<div id="text408182"><img src="/get_file?id=1">Условие</div>
<div id="body408182">Коротко</div>
```

and assert the created `TaskVariant.content` contains `id="text408182"` / `get_file`.

---

## Operational Notes (how to use after deploy)

- Re-importing existing tasks: In the “Импорт с РешуЕГЭ” admin page, uncheck “Пропускать уже загруженные”, provide any of the bundle ids (type 1 is enough), and re-run import for types 1–5. This will update stored HTML and trigger image download for the expanded statement.

