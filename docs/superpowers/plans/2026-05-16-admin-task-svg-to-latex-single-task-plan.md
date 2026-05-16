# Admin Task Edit + Single-Task SVG→LaTeX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В Django admin редактировать условие/решение конкретной задачи (classic) и запускать SVG→LaTeX для одной задачи с предпросмотром и применением.

**Architecture:** Добавляем `TaskVariantInline` к `TaskAdmin` (фильтр theme=classic) и кастомные admin URLs (preview/apply) внутри `TaskAdmin.get_urls()`. Логику конвертации “для одной задачи” реализуем в `core/services_svg_to_latex.py` по аналогии с `convert_svg_to_latex_for_task_type`.

**Tech Stack:** Django admin, Django templates, существующие сервисы `services_svg_to_latex.py`, `tex_replace.py`.

---

## File map

**Modify:**
- `/workspace/core/admin.py` — inline, кнопка, custom URLs, views preview/apply.
- `/workspace/core/services_svg_to_latex.py` — новая функция конвертации для одной задачи.

**Create:**
- `/workspace/core/templates/admin/core/task/change_form.html` — добавить кнопку в object-tools.
- `/workspace/core/templates/admin/core/task/svg_to_latex_preview.html` — страница предпросмотра + кнопка “Применить”.
- `/workspace/core/tests/test_admin_task_svg_to_latex_single_task.py` — тесты preview/apply.

---

### Task 1: Добавить конвертацию SVG→LaTeX для одной задачи в сервис

**Files:**
- Modify: `/workspace/core/services_svg_to_latex.py`
- Test: `/workspace/core/tests/test_admin_task_svg_to_latex_single_task.py` (тест на сервис можно встроить)

- [ ] **Step 1: Write failing test for service (dry_run не меняет БД)**

```python
def test_convert_svg_to_latex_for_task_dry_run_does_not_modify_variant(self):
    # создать Task + TaskVariant(classic) c <img src="...svg"> в content
    # вызвать convert_svg_to_latex_for_task(..., dry_run=True)
    # убедиться, что в БД variant.content не изменился
    # и что в отчёте есть replaced>0
    pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_admin_task_svg_to_latex_single_task -v 2`  
Expected: FAIL (функции нет).

- [ ] **Step 3: Implement minimal service**

Добавить функцию:

```python
def convert_svg_to_latex_for_task(*, task_id: int, theme: str = "classic", dry_run: bool = False) -> dict:
    # найти TaskVariant(task_id, theme)
    # new_content/new_solution через replace_svg_images_with_latex + fix_* + normalize_task_html
    # если not dry_run: сохранить content/solution
    # вернуть stats + before/after для preview
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_admin_task_svg_to_latex_single_task -v 2`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/services_svg_to_latex.py core/tests/test_admin_task_svg_to_latex_single_task.py
git commit -m "feat: add svg-to-latex conversion for a single task"
```

---

### Task 2: Inline-редактирование TaskVariant(classic) в TaskAdmin

**Files:**
- Modify: `/workspace/core/admin.py`

- [ ] **Step 1: Add TaskVariantInline (classic only)**

```python
class TaskVariantClassicInline(admin.StackedInline):
    model = TaskVariant
    extra = 0
    max_num = 1
    fields = ("theme", "content", "solution")
    readonly_fields = ("theme",)
    def get_queryset(...): return super().get_queryset(...).filter(theme="classic")
```

- [ ] **Step 2: Attach inline to TaskAdmin**

- [ ] **Step 3: Smoke-test admin loads**

Run: `python manage.py test core.tests.test_admin_task_svg_to_latex_single_task -v 2`

- [ ] **Step 4: Commit**

```bash
git add core/admin.py
git commit -m "feat: allow editing classic TaskVariant inline in admin"
```

---

### Task 3: Кнопка SVG→LaTeX + preview/apply страницы в Django admin

**Files:**
- Modify: `/workspace/core/admin.py`
- Create: `/workspace/core/templates/admin/core/task/change_form.html`
- Create: `/workspace/core/templates/admin/core/task/svg_to_latex_preview.html`
- Test: `/workspace/core/tests/test_admin_task_svg_to_latex_single_task.py`

- [ ] **Step 1: Write failing tests for preview/apply endpoints**

```python
def test_admin_preview_does_not_modify_db(self): ...
def test_admin_apply_modifies_variant(self): ...
```

- [ ] **Step 2: Run tests to verify RED**

Run: `python manage.py test core.tests.test_admin_task_svg_to_latex_single_task -v 2`  
Expected: FAIL (URL/view/template нет).

- [ ] **Step 3: Implement admin URLs + views**

В `TaskAdmin.get_urls()` добавить пути:
- `<object_id>/svg-to-latex-preview/` (GET)
- `<object_id>/svg-to-latex-apply/` (POST)

Preview вызывает сервис с `dry_run=True` и рендерит шаблон.
Apply вызывает сервис с `dry_run=False`, пишет `messages.success` и редиректит обратно на change page.

- [ ] **Step 4: Add change_form template with button**

Кнопка в object-tools на preview URL.

- [ ] **Step 5: Run tests to verify GREEN**

Run: `python manage.py test core.tests.test_admin_task_svg_to_latex_single_task -v 2`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/admin.py core/templates/admin/core/task/change_form.html core/templates/admin/core/task/svg_to_latex_preview.html core/tests/test_admin_task_svg_to_latex_single_task.py
git commit -m "feat: add single-task svg-to-latex preview/apply in admin"
```

---

### Task 4: Final verification + push

- [ ] Run: `python manage.py test core.tests.test_admin_task_svg_to_latex_single_task -v 2`
- [ ] Run: `git push origin main`

