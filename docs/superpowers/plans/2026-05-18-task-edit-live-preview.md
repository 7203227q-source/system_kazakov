# Task Edit Live Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add live preview (condition/solution/answer) with MathJax and images to the admin task edit page in the task bank.

**Architecture:** Add an admin-only JSON endpoint that renders preview HTML by applying the same fix/normalize pipeline as production, then update `task_edit.html` to show a live-updating preview panel (debounced fetch + MathJax typeset + image modal bindings).

**Tech Stack:** Django views/templates, Django messages, Tailwind, MathJax v3, existing HTML/LaTeX fix utilities, Django TestCase.

---

## File Map

**Modify**
- `core/templates/core/task_edit.html` (layout: editor + preview; MathJax; JS live update; reuse image modal)
- `core/urls.py` (add preview endpoint route)
- `core/views.py` (add preview endpoint view)

**Create**
- `core/tests/test_task_edit_live_preview.py` (endpoint + permissions tests)

---

### Task 1: Add preview endpoint (admin-only)

**Files:**
- Modify: `core/urls.py`
- Modify: `core/views.py`
- Test: `core/tests/test_task_edit_live_preview.py`

- [ ] **Step 1: Write failing tests for preview endpoint**

Create `core/tests/test_task_edit_live_preview.py`:

```python
import json

from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, Topic, User


class TaskEditLivePreviewEndpointTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pw", role="admin")
        self.tutor = User.objects.create_user(username="tutor", password="pw", role="tutor")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="0")

    def test_admin_can_render_preview_json(self):
        self.client.force_login(self.admin)
        url = reverse("task_bank_task_render_preview", args=[self.task.id])
        payload = {"content": '<p><img src="/formula/svg/1.svg" alt="x"/></p>', "solution": "<p>y</p>"}
        res = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("content_html", data)
        self.assertIn("solution_html", data)
        self.assertIn("<img", data["content_html"])

    def test_non_admin_is_redirected(self):
        self.client.force_login(self.tutor)
        url = reverse("task_bank_task_render_preview", args=[self.task.id])
        res = self.client.post(url, data=json.dumps({"content": "x", "solution": ""}), content_type="application/json")
        self.assertEqual(res.status_code, 302)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python manage.py test core.tests.test_task_edit_live_preview.TaskEditLivePreviewEndpointTests -v 2
```

Expected: FAIL because the URL/view does not exist.

- [ ] **Step 3: Add URL route**

In `core/urls.py` add:

```python
path(
    "tutor/tasks/<int:task_id>/render-preview/",
    views.task_bank_task_render_preview,
    name="task_bank_task_render_preview",
),
```

- [ ] **Step 4: Implement view**

In `core/views.py` add:

```python
@login_required
@require_POST
def task_bank_task_render_preview(request, task_id: int):
    if request.user.role != "admin":
        return redirect("tutor_task_bank")

    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except Exception:
        payload = {}

    content = payload.get("content") or ""
    solution = payload.get("solution") or ""

    from core.task_html import normalize_task_html
    from core.tex_replace import fix_latex_tokens_in_html, fix_math_words_in_html

    content2, _ = fix_latex_tokens_in_html(content)
    content3 = normalize_task_html(content2)
    content4, _ = fix_math_words_in_html(content3)

    solution2, _ = fix_latex_tokens_in_html(solution)
    solution3 = normalize_task_html(solution2) if solution2 else solution2
    solution4, _ = fix_math_words_in_html(solution3) if solution3 else (solution3, 0)

    return JsonResponse({"content_html": content4, "solution_html": solution4 or ""})
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
python manage.py test core.tests.test_task_edit_live_preview.TaskEditLivePreviewEndpointTests -v 2
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/urls.py core/views.py core/tests/test_task_edit_live_preview.py
git commit -m "feat(task-edit): add render-preview endpoint for live preview"
```

---

### Task 2: Add live preview UI (editor + preview + MathJax + images)

**Files:**
- Modify: `core/templates/core/task_edit.html`
- Test: `core/tests/test_task_edit_live_preview.py`

- [ ] **Step 1: Extend tests to ensure edit page contains preview containers**

Append to `core/tests/test_task_edit_live_preview.py`:

```python
from core.models import TaskVariant


class TaskEditLivePreviewPageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pw", role="admin")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="0")
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>x</p>", solution="<p>y</p>")

    def test_edit_page_has_preview_blocks(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("task_bank_task_edit", args=[self.task.id]))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")
        self.assertIn('id="live-preview-content"', html)
        self.assertIn('id="live-preview-solution"', html)
        self.assertIn('id="live-preview-answer"', html)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python manage.py test core.tests.test_task_edit_live_preview.TaskEditLivePreviewPageTests -v 2
```

Expected: FAIL until template is updated.

- [ ] **Step 3: Update template layout**

In `core/templates/core/task_edit.html`:
- add MathJax config + script (same as `tutor_task_bank.html`)
- include `core/image_modal.html`
- change main layout into responsive grid:
  - left: current forms/textarea + save
  - right: preview panel
- add preview containers:

```html
<div class="bg-white border border-gray-200 rounded-xl p-4">
  <div class="font-bold text-gray-800 mb-3">Предпросмотр</div>
  <div class="text-sm mb-4">
    <span class="text-gray-500 mr-2">Ответ:</span>
    <span id="live-preview-answer" class="font-bold text-green-700">{{ task.correct_answer }}</span>
  </div>
  <div class="font-bold mb-2">Условие</div>
  <div id="live-preview-content" class="prose max-w-none text-sm"></div>
  <div class="font-bold mt-4 mb-2">Решение</div>
  <div id="live-preview-solution" class="prose max-w-none text-sm"></div>
</div>
```

- [ ] **Step 4: Add JS live preview**

In the same template, add JS:
- `debounce` (700ms)
- `renderPreview()` fetches JSON from `task_bank_task_render_preview`
- updates `innerHTML` of preview blocks
- calls `MathJax.typesetPromise()` if available
- binds image modal for images in preview (reusing functions from included partial)

Suggested snippet:

```html
<script>
  function debounce(fn, ms) {
    let t = null;
    return function(...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  function bindPreviewImages() {
    const images = document.querySelectorAll('#live-preview-content img, #live-preview-solution img');
    images.forEach(img => {
      if (img.classList.contains('tex')) return;
      img.classList.add('cursor-zoom-in', 'hover:opacity-80', 'transition-opacity', 'rounded');
      img.addEventListener('click', (e) => {
        e.preventDefault();
        openImageModal(img.src);
      });
    });
  }

  async function renderPreview() {
    const contentEl = document.querySelector('textarea[name="content"]');
    const solutionEl = document.querySelector('textarea[name="solution"]');
    const csrf = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    if (!contentEl || !solutionEl || !csrf) return;

    const url = "{% url 'task_bank_task_render_preview' task.id %}";
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({ content: contentEl.value || "", solution: solutionEl.value || "" }),
    });
    if (!res.ok) return;
    const data = await res.json();

    const outContent = document.getElementById('live-preview-content');
    const outSolution = document.getElementById('live-preview-solution');
    if (outContent) outContent.innerHTML = data.content_html || '';
    if (outSolution) outSolution.innerHTML = data.solution_html || '';

    if (window.MathJax && window.MathJax.typesetPromise) {
      await window.MathJax.typesetPromise();
    }
    bindPreviewImages();
  }

  document.addEventListener('DOMContentLoaded', () => {
    const contentEl = document.querySelector('textarea[name="content"]');
    const solutionEl = document.querySelector('textarea[name="solution"]');
    const debounced = debounce(renderPreview, 700);
    if (contentEl) contentEl.addEventListener('input', debounced);
    if (solutionEl) solutionEl.addEventListener('input', debounced);
    renderPreview();
  });
</script>
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
python manage.py test core.tests.test_task_edit_live_preview -v 2
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/templates/core/task_edit.html core/tests/test_task_edit_live_preview.py
git commit -m "feat(task-edit): add live preview panel with mathjax and images"
```

---

### Task 3: Full verification and push

**Files:**
- Modify: (only if fixes needed)

- [ ] **Step 1: Run focused test suite**

Run:

```bash
python manage.py test core.tests.test_task_bank_task_edit_page core.tests.test_task_bank_task_svg_to_latex core.tests.test_task_edit_live_preview -v 1
```

Expected: PASS.

- [ ] **Step 2: Push to GitHub main**

Run:

```bash
git push origin main
```

---

## Plan Self-Review

- Spec coverage: live preview, answer display, MathJax, images, admin-only endpoint, tests.
- Placeholder scan: no TODO/TBD; code blocks and commands provided for each step.
- Naming consistency: endpoint name `task_bank_task_render_preview`, container ids `live-preview-*`.

