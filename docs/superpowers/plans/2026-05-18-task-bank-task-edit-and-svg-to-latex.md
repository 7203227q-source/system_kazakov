# Task Bank Task Edit + SVG→LaTeX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an “Редактировать” button next to “ИИ: Регенерировать” in the task bank, opening an admin-only edit page with inline editing of classic content/solution plus SVG→LaTeX preview/apply actions.

**Architecture:** Implement a dedicated edit page in the existing task bank UI (`tutor_task_bank`) rather than Django-admin. Add new views + URL routes for edit and SVG→LaTeX preview/apply, reusing `replace_svg_images_with_latex` pipeline used elsewhere.

**Tech Stack:** Django views/templates, Django messages, existing `core.services_svg_to_latex` and `core.tex_replace` utilities, Django TestCase.

---

## File Map

**Modify**
- `core/templates/core/tutor_task_bank.html` (add “Редактировать” button next to “ИИ: Регенерировать” for admin)
- `core/urls.py` (add routes for edit + SVG→LaTeX preview/apply)
- `core/views.py` (implement edit + svg-to-latex views with admin-only permission checks)
- `core/services_svg_to_latex.py` (add single-task converter that returns before/after and optionally persists)

**Create**
- `core/templates/core/task_edit.html` (admin edit page with form + SVG→LaTeX preview/apply UI)

**Test**
- `core/tests/test_task_bank_task_edit_page.py` (edit page loads + saves variant content/solution)
- `core/tests/test_task_bank_task_svg_to_latex.py` (preview does not persist; apply persists)

---

### Task 1: Add “Редактировать” button in task bank list

**Files:**
- Modify: `core/templates/core/tutor_task_bank.html`
- Test: `core/tests/test_task_bank_task_edit_page.py`

- [ ] **Step 1: Write failing test that task bank page includes edit link for admin**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, Topic, User, TaskVariant


class TaskBankEditButtonTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pw", role="admin")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="0")
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>x</p>", solution="<p>y</p>")

    def test_task_bank_has_edit_button_for_admin(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("tutor_task_bank"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("Редактировать", res.content.decode("utf-8"))
        self.assertIn(f"/tutor/tasks/{self.task.id}/edit/", res.content.decode("utf-8"))
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest core/tests/test_task_bank_task_edit_page.py::TaskBankEditButtonTests::test_task_bank_has_edit_button_for_admin -q
```

Expected: FAIL because the link is not present.

- [ ] **Step 3: Implement the button next to “ИИ: Регенерировать”**

Update the admin block near the existing button in:
`core/templates/core/tutor_task_bank.html` around:

```html
{% if user.role == 'admin' %}
<button type="button" onclick="openRegenModal({{ task.id }})" ...>ИИ: Регенерировать</button>
{% endif %}
```

Add a link:

```html
<a href="{% url 'task_bank_task_edit' task.id %}"
   class="text-gray-700 hover:text-gray-900 text-sm font-bold flex items-center transition">
  <i class="fas fa-pen-to-square mr-2"></i> Редактировать
</a>
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
pytest core/tests/test_task_bank_task_edit_page.py::TaskBankEditButtonTests::test_task_bank_has_edit_button_for_admin -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/templates/core/tutor_task_bank.html core/tests/test_task_bank_task_edit_page.py
git commit -m "feat(task-bank): add edit button for tasks"
```

---

### Task 2: Add admin-only task edit page (classic content/solution)

**Files:**
- Modify: `core/urls.py`
- Modify: `core/views.py`
- Create: `core/templates/core/task_edit.html`
- Test: `core/tests/test_task_bank_task_edit_page.py`

- [ ] **Step 1: Extend the failing test to cover edit GET and POST**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, Topic, User, TaskVariant


class TaskBankEditPageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pw", role="admin")
        self.tutor = User.objects.create_user(username="tutor", password="pw", role="tutor")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="0")
        self.variant = TaskVariant.objects.create(task=self.task, theme="classic", content="<p>x</p>", solution="<p>y</p>")

    def test_edit_page_admin_only(self):
        self.client.force_login(self.tutor)
        res = self.client.get(reverse("task_bank_task_edit", args=[self.task.id]))
        self.assertEqual(res.status_code, 302)

        self.client.force_login(self.admin)
        res2 = self.client.get(reverse("task_bank_task_edit", args=[self.task.id]))
        self.assertEqual(res2.status_code, 200)
        self.assertIn("Редактирование задачи", res2.content.decode("utf-8"))

    def test_edit_page_updates_classic_variant(self):
        self.client.force_login(self.admin)
        url = reverse("task_bank_task_edit", args=[self.task.id])
        res = self.client.post(url, data={"content": "<p>new</p>", "solution": "<p>sol</p>"})
        self.assertEqual(res.status_code, 302)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.content, "<p>new</p>")
        self.assertEqual(self.variant.solution, "<p>sol</p>")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest core/tests/test_task_bank_task_edit_page.py::TaskBankEditPageTests -q
```

Expected: FAIL because route/view/template do not exist.

- [ ] **Step 3: Add URL route**

In `core/urls.py` add:

```python
path("tutor/tasks/<int:task_id>/edit/", views.task_bank_task_edit, name="task_bank_task_edit"),
```

- [ ] **Step 4: Implement view**

In `core/views.py` add:

```python
from django.shortcuts import get_object_or_404
from core.models import Task, TaskVariant

@login_required
def task_bank_task_edit(request, task_id: int):
    if request.user.role != "admin":
        return redirect("tutor_task_bank")
    task = get_object_or_404(Task.objects.select_related("topic", "task_type"), id=task_id)
    variant = task.variants.filter(theme="classic").first()
    if not variant:
        variant = TaskVariant.objects.create(task=task, theme="classic", content="", solution="")

    if request.method == "POST":
        variant.content = request.POST.get("content", "") or ""
        variant.solution = request.POST.get("solution", "") or ""
        variant.save(update_fields=["content", "solution"])
        messages.success(request, "Сохранено.")
        return redirect("task_bank_task_edit", task_id=task.id)

    return render(request, "core/task_edit.html", {"task": task, "variant": variant})
```

- [ ] **Step 5: Create template**

Create `core/templates/core/task_edit.html` with:
- title “Редактирование задачи #ID”
- textarea inputs named `content` and `solution` prefilled from `variant`
- save button
- include the SVG→LaTeX buttons placeholders (wired in Task 3)

Minimal skeleton:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Редактирование задачи</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50">
  <div class="max-w-5xl mx-auto p-6">
    <div class="flex items-center justify-between mb-6">
      <div class="font-bold text-xl">Редактирование задачи #{{ task.id }}</div>
      <a class="text-indigo-700 font-bold" href="{% url 'tutor_task_bank' %}">← Назад</a>
    </div>

    <form method="post" class="space-y-4">
      {% csrf_token %}
      <div>
        <div class="font-bold mb-2">Условие (classic)</div>
        <textarea name="content" class="w-full h-64 border rounded p-3 font-mono text-sm">{{ variant.content }}</textarea>
      </div>
      <div>
        <div class="font-bold mb-2">Решение (classic)</div>
        <textarea name="solution" class="w-full h-64 border rounded p-3 font-mono text-sm">{{ variant.solution }}</textarea>
      </div>
      <div class="flex items-center gap-3">
        <button type="submit" class="px-4 py-2 rounded bg-indigo-700 text-white font-bold">Сохранить</button>
      </div>
    </form>
  </div>
</body>
</html>
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
pytest core/tests/test_task_bank_task_edit_page.py::TaskBankEditPageTests -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add core/urls.py core/views.py core/templates/core/task_edit.html core/tests/test_task_bank_task_edit_page.py
git commit -m "feat(task-bank): add admin task edit page for classic variant"
```

---

### Task 3: Add SVG→LaTeX preview/apply on the edit page (single task)

**Files:**
- Modify: `core/services_svg_to_latex.py`
- Modify: `core/urls.py`
- Modify: `core/views.py`
- Modify: `core/templates/core/task_edit.html`
- Test: `core/tests/test_task_bank_task_svg_to_latex.py`

- [ ] **Step 1: Write failing tests for preview/apply behavior**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, Topic, User, TaskVariant


class TaskBankSvgToLatexTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pw", role="admin")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="0")
        self.variant = TaskVariant.objects.create(
            task=self.task,
            theme="classic",
            content='<p><img src="/formula/svg/1.svg" alt="x"/></p>',
            solution="",
        )

    def test_preview_does_not_persist(self):
        self.client.force_login(self.admin)
        url = reverse("task_bank_task_svg_to_latex_preview", args=[self.task.id])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.variant.refresh_from_db()
        self.assertIn("<img", self.variant.content)

    def test_apply_persists(self):
        self.client.force_login(self.admin)
        url = reverse("task_bank_task_svg_to_latex_apply", args=[self.task.id])
        res = self.client.post(url)
        self.assertEqual(res.status_code, 302)
        self.variant.refresh_from_db()
        self.assertNotIn("<img", self.variant.content)
        self.assertIn("$", self.variant.content)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest core/tests/test_task_bank_task_svg_to_latex.py::TaskBankSvgToLatexTests -q
```

Expected: FAIL because converter + routes do not exist.

- [ ] **Step 3: Add a single-task converter to services**

In `core/services_svg_to_latex.py` add a function:

```python
from core.models import TaskVariant
from core.task_html import normalize_task_html
from core.tex_replace import fix_latex_tokens_in_html, fix_math_words_in_html, replace_svg_images_with_latex

def convert_svg_to_latex_for_task(*, task_id: int, theme: str = "classic", dry_run: bool = False) -> dict:
    v = (
        TaskVariant.objects.select_related("task")
        .filter(task_id=task_id, theme=theme)
        .first()
    )
    if not v:
        raise ValueError("TaskVariant not found")

    old_content = v.content or ""
    old_solution = v.solution or ""

    new_content, replaced_content = replace_svg_images_with_latex(old_content)
    new_solution, replaced_solution = replace_svg_images_with_latex(old_solution)

    new_content, fixed_content = fix_latex_tokens_in_html(new_content)
    new_solution, fixed_solution = fix_latex_tokens_in_html(new_solution)
    new_content = normalize_task_html(new_content)
    new_solution = normalize_task_html(new_solution) if new_solution else new_solution

    new_content, fixed_words_content = fix_math_words_in_html(new_content)
    new_solution, fixed_words_solution = fix_math_words_in_html(new_solution) if new_solution else (new_solution, 0)

    replaced_total = (
        replaced_content
        + replaced_solution
        + fixed_content
        + fixed_solution
        + fixed_words_content
        + fixed_words_solution
    )

    changed = (new_content != old_content) or (new_solution != old_solution)
    if changed and not dry_run:
        v.content = new_content
        v.solution = new_solution
        v.save(update_fields=["content", "solution"])

    return {
        "engine": "svg-to-latex:single:v1",
        "dry_run": dry_run,
        "task_id": task_id,
        "theme": theme,
        "changed": changed,
        "replaced": replaced_total,
        "old_content": old_content,
        "old_solution": old_solution,
        "new_content": new_content,
        "new_solution": new_solution,
    }
```

- [ ] **Step 4: Add routes**

In `core/urls.py` add:

```python
path(
    "tutor/tasks/<int:task_id>/svg-to-latex-preview/",
    views.task_bank_task_svg_to_latex_preview,
    name="task_bank_task_svg_to_latex_preview",
),
path(
    "tutor/tasks/<int:task_id>/svg-to-latex-apply/",
    views.task_bank_task_svg_to_latex_apply,
    name="task_bank_task_svg_to_latex_apply",
),
```

- [ ] **Step 5: Implement views (admin-only)**

In `core/views.py` add:

```python
@login_required
def task_bank_task_svg_to_latex_preview(request, task_id: int):
    if request.user.role != "admin":
        return redirect("tutor_task_bank")
    from .services_svg_to_latex import convert_svg_to_latex_for_task
    report = convert_svg_to_latex_for_task(task_id=task_id, theme="classic", dry_run=True)
    task = Task.objects.get(id=task_id)
    variant = task.variants.filter(theme="classic").first()
    return render(request, "core/task_edit.html", {"task": task, "variant": variant, "svg_report": report})


@login_required
@require_POST
def task_bank_task_svg_to_latex_apply(request, task_id: int):
    if request.user.role != "admin":
        return redirect("tutor_task_bank")
    from .services_svg_to_latex import convert_svg_to_latex_for_task
    report = convert_svg_to_latex_for_task(task_id=task_id, theme="classic", dry_run=False)
    if report.get("changed"):
        messages.success(request, "SVG→LaTeX применено.")
    else:
        messages.info(request, "Изменений не найдено.")
    return redirect("task_bank_task_edit", task_id=task_id)
```

- [ ] **Step 6: Wire buttons + preview UI into template**

In `core/templates/core/task_edit.html` add:
- A “SVG→LaTeX: предпросмотр” link to `task_bank_task_svg_to_latex_preview`
- A “SVG→LaTeX: применить” POST form to `task_bank_task_svg_to_latex_apply`
- If `svg_report` is present, render “до/после” in two textareas (read-only) or two blocks.

Example snippet:

```html
<div class="flex items-center gap-3">
  <a href="{% url 'task_bank_task_svg_to_latex_preview' task.id %}" class="px-4 py-2 rounded bg-gray-900 text-white font-bold">SVG→LaTeX: предпросмотр</a>
  <form method="post" action="{% url 'task_bank_task_svg_to_latex_apply' task.id %}">
    {% csrf_token %}
    <button type="submit" class="px-4 py-2 rounded bg-indigo-700 text-white font-bold">SVG→LaTeX: применить</button>
  </form>
</div>
{% if svg_report %}
<div class="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
  <div>
    <div class="font-bold mb-2">До</div>
    <textarea readonly class="w-full h-64 border rounded p-3 font-mono text-xs">{{ svg_report.old_content }}</textarea>
  </div>
  <div>
    <div class="font-bold mb-2">После</div>
    <textarea readonly class="w-full h-64 border rounded p-3 font-mono text-xs">{{ svg_report.new_content }}</textarea>
  </div>
</div>
{% endif %}
```

- [ ] **Step 7: Run tests to verify pass**

Run:

```bash
pytest core/tests/test_task_bank_task_svg_to_latex.py::TaskBankSvgToLatexTests -q
pytest core/tests/test_task_bank_task_edit_page.py::TaskBankEditPageTests -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/services_svg_to_latex.py core/urls.py core/views.py core/templates/core/task_edit.html core/tests/test_task_bank_task_svg_to_latex.py
git commit -m "feat(task-bank): add svg-to-latex preview/apply on task edit page"
```

---

## Plan Self-Review

- Coverage: button in task list + edit page + svg preview/apply + admin-only checks + tests all present.
- Placeholder scan: no TBD/TODO steps; each change includes concrete code and commands.
- Naming consistency: routes use `task_bank_task_edit`, `task_bank_task_svg_to_latex_preview`, `task_bank_task_svg_to_latex_apply`.

---

## Execution Choice

Plan complete and saved to `docs/superpowers/plans/2026-05-18-task-bank-task-edit-and-svg-to-latex.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

