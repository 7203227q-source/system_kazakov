# Admin Task Modal Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в platform-admin экран “Задачи” с поиском/вводом ID и модалкой, где админ может просматривать/редактировать условие/решение/ответ, загружать картинки (с автo-вставкой в HTML) и запускать “Fix LaTeX” (нормализация HTML) для выбранной задачи.

**Architecture:** Новый экран `/platform-admin/tasks/` (server-rendered) + набор JSON endpoints (get/update/fix-latex/upload). Модалка на чистом JS (fetch + DOM) без перезагрузки.

**Tech Stack:** Django (views/templates), Tailwind (как уже в admin templates), vanilla JS, Django TestCase.

---

## File Structure

**Create**
- `core/templates/core/admin_tasks.html`
- `core/tests/test_admin_tasks_modal_endpoints.py`

**Modify**
- `core/urls.py` — добавить новые маршруты platform-admin
- `core/views.py` — добавить views для tasks page + JSON endpoints
- `core/templates/core/admin_dashboard.html` — добавить пункт меню “Задачи”

---

### Task 1: Add failing tests for new endpoints

**Files:**
- Create: `core/tests/test_admin_tasks_modal_endpoints.py`

- [ ] **Step 1: Write failing tests**

```python
import json
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User


class AdminTasksModalEndpointsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pw", role="admin")
        self.student = User.objects.create_user(username="student", password="pw", role="student")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="42", fipi_id="x1")
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>c</p>", solution="<p>s</p>")

    def test_admin_tasks_page_requires_admin(self):
        url = reverse("admin_tasks")
        self.client.force_login(self.student)
        res = self.client.get(url)
        self.assertNotEqual(res.status_code, 200)

        self.client.force_login(self.admin)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Задачи")

    def test_get_task_json(self):
        self.client.force_login(self.admin)
        url = reverse("admin_task_json", args=[self.task.id])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["task"]["id"], self.task.id)
        self.assertEqual(data["task"]["correct_answer"], "42")
        self.assertIn("content_html", data["variant"])

    def test_update_task(self):
        self.client.force_login(self.admin)
        url = reverse("admin_task_update", args=[self.task.id])
        res = self.client.post(
            url,
            data=json.dumps({"correct_answer": "43", "content_html": "<p>c2</p>", "solution_html": "<p>s2</p>"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.correct_answer, "43")
        v = TaskVariant.objects.get(task=self.task, theme="classic")
        self.assertIn("c2", v.content)

    def test_fix_latex(self):
        self.client.force_login(self.admin)
        v = TaskVariant.objects.get(task=self.task, theme="classic")
        v.content = '<p><img src="https://example.com/f.svg" alt="дробь: числитель: 1, знаменатель: 2 конец дроби"></p>'
        v.save(update_fields=["content"])

        url = reverse("admin_task_fix_latex", args=[self.task.id])
        res = self.client.post(url)
        self.assertEqual(res.status_code, 200)
        v.refresh_from_db()
        self.assertIn("$", v.content)

    def test_upload_image(self):
        self.client.force_login(self.admin)
        url = reverse("admin_task_upload_image")
        file = SimpleUploadedFile("x.png", b"fake", content_type="image/png")
        res = self.client.post(url, data={"file": file, "target": "content"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["url"].startswith("/media/"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
python manage.py test core.tests.test_admin_tasks_modal_endpoints -v 2
```

Expected: FAIL (routes/views/templates not implemented).

---

### Task 2: Add URLs

**Files:**
- Modify: `core/urls.py`

- [ ] **Step 1: Add routes**

Add:
- `path("platform-admin/tasks/", views.admin_tasks, name="admin_tasks")`
- `path("platform-admin/tasks/<int:task_id>/json/", views.admin_task_json, name="admin_task_json")`
- `path("platform-admin/tasks/<int:task_id>/update/", views.admin_task_update, name="admin_task_update")`
- `path("platform-admin/tasks/<int:task_id>/fix-latex/", views.admin_task_fix_latex, name="admin_task_fix_latex")`
- `path("platform-admin/tasks/upload-image/", views.admin_task_upload_image, name="admin_task_upload_image")`

- [ ] **Step 2: Re-run tests (still failing)**

---

### Task 3: Implement views (page + endpoints)

**Files:**
- Modify: `core/views.py`

- [ ] **Step 1: Implement `admin_tasks` page view**

Behavior:
- admin-only
- supports `q` search:
  - if `q` is digit → filter by id
  - else search in `fipi_id` and `variants__content` (icontains)
- limit results (e.g., 50)
- render template `core/admin_tasks.html` with results.

- [ ] **Step 2: Implement `admin_task_json`**

Return payload described in spec with `TaskVariant(theme="classic")`.

- [ ] **Step 3: Implement `admin_task_update`**

Accept JSON body and persist:
- `Task.correct_answer`
- `TaskVariant.content/solution` (create if missing)

- [ ] **Step 4: Implement `admin_task_fix_latex`**

Call pipeline (existing helpers):
- `replace_svg_images_with_latex`, `fix_latex_tokens_in_html`, `normalize_task_html`, `fix_math_words_in_html`
Save back to variant, return updated JSON.

- [ ] **Step 5: Implement `admin_task_upload_image`**

Use `default_storage.save` to save into `tasks/admin_upload/<uuid>.<ext>` and return `/media/<path>`.
Validate content-type begins with `image/` or SVG bytes.

---

### Task 4: Create template with modal + JS

**Files:**
- Create: `core/templates/core/admin_tasks.html`
- Modify: `core/templates/core/admin_dashboard.html` (sidebar link)

- [ ] **Step 1: Add sidebar link in admin_dashboard.html**

Add link to `{% url 'admin_tasks' %}` with icon `fa-tasks`.

- [ ] **Step 2: Build admin_tasks.html**

Must include:
- layout consistent with admin pages (sidebar + header)
- Quick open by id input
- Search form + results table
- Hidden modal + overlay
- JS:
  - `openTaskModal(taskId)` → fetch json, fill preview and editor fields
  - `saveTask()` → POST update
  - `fixLatex()` → POST fix-latex, refresh preview + fields
  - `uploadImage(target)` → POST form-data, insert `<img src="...">` at cursor in corresponding textarea
  - Safe error display in modal

---

### Task 5: Run tests and commit

- [ ] **Step 1: Run tests**

```bash
python manage.py test core.tests.test_admin_tasks_modal_endpoints -v 2
```

- [ ] **Step 2: Smoke run relevant existing tests**

```bash
python manage.py test core.tests.test_admin_svg_to_latex_convert -v 2
```

- [ ] **Step 3: Commit**

```bash
git add core/urls.py core/views.py core/templates/core/admin_dashboard.html core/templates/core/admin_tasks.html core/tests/test_admin_tasks_modal_endpoints.py
git commit -m "feat(admin): task modal editor with latex fix and uploads"
```

