# Physics KIM Reference (FAB + Modal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a floating “?” button that opens a KIM-only physics reference modal for students when solving Physics (ЕГЭ/ОГЭ), available both in assignments and in practice.

**Architecture:** Create a reusable template include with (1) FAB button, (2) modal with tabbed content, (3) small JS to open/close and switch tabs. Render it conditionally only for Physics subject and only for ЕГЭ/ОГЭ formats. Reference content is hard-coded HTML fragments (EGE/OGE) stored in repo templates.

**Tech Stack:** Django templates, Tailwind utility classes, minimal vanilla JS, Django tests (view/template gating).

---

## File Map

**Create**
- `core/templates/core/includes/_physics_kim_reference_content_ege.html`
- `core/templates/core/includes/_physics_kim_reference_content_oge.html`
- `core/templates/core/includes/_physics_kim_reference_widget.html`
- `core/tests/test_physics_kim_reference_widget.py`

**Modify**
- [student_solve_assignment.html](file:///workspace/core/templates/core/student_solve_assignment.html)
- [student_practice.html](file:///workspace/core/templates/core/student_practice.html)
- [views.py](file:///workspace/core/views.py): `student_solve_assignment`, `student_practice` to pass `physics_kim_reference_context`

---

## Runtime Rules

### When to show
- Only if the current subject is Physics:
  - Assignment solve page: `assignment.exam_format.subject.name` contains `Физ` (case-insensitive) OR any task topic subject contains `Физ`.
  - Practice page: `active_subject_id` subject name contains `Физ`.
- Only if the exam format is ЕГЭ or ОГЭ:
  - Use `exam_format.name` contains `ЕГЭ` or contains `ОГЭ` (case-insensitive).

### Which reference to show
- If format contains `ЕГЭ` → show EGE content.
- If format contains `ОГЭ` → show OGE content.

### UI
- FAB: circular, bottom-right, “?” icon.
- Modal: tabs (A-choice) with fixed labels: `Константы / Приставки / Единицы / Прочее`.
- Content: “только то что в КИМ” (no extra formulas/tables beyond KIM reference).

---

## Task 1: Write failing tests (TDD)

**Files:**
- Create: [test_physics_kim_reference_widget.py](file:///workspace/core/tests/test_physics_kim_reference_widget.py)

- [ ] **Step 1: Assignment page shows widget for Physics EGE**

Create:
- student + tutor
- Physics subject + EGE exam format
- assignment with `exam_format=physics_ege`
- at least one task in Physics

GET `student_solve_assignment` and assert HTML contains a unique marker string like `id="physics-kim-fab"` (we will add it).

- [ ] **Step 2: Assignment page does NOT show widget for non-Physics**

Create Math subject + EGE format assignment; assert marker not present.

- [ ] **Step 3: Practice page shows widget for Physics OGE**

Create StudentSubjectProfile with Physics subject and exam_format name containing `ОГЭ`; GET `/student/practice/?subject_id=...` and assert marker present.

- [ ] **Step 4: Run tests and watch them fail**

```bash
python manage.py test core.tests.test_physics_kim_reference_widget -v 2
```

---

## Task 2: Add context flags in views (minimal code)

**Files:**
- Modify: [views.py](file:///workspace/core/views.py)

- [ ] **Step 1: Add helper for deciding (subject_name, exam_format_name)**

Implement local helper near the two views (or inline):
- normalize to lowercase
- `is_physics = "физ" in subject_name`
- `is_ege = "егэ" in exam_format_name`
- `is_oge = "огэ" in exam_format_name`
- `enabled = is_physics and (is_ege or is_oge)`
- `kind = "ege" if is_ege else "oge"`

- [ ] **Step 2: student_solve_assignment passes widget context**

Add to render context:
```python
"physics_kim_ref_enabled": enabled,
"physics_kim_ref_kind": kind,
```
Compute:
- subject/exam_format from `assignment.exam_format` when present; fallback to first task’s subject.

- [ ] **Step 3: student_practice passes widget context**

Reuse `active_profile.exam_format` and the selected subject name.

- [ ] **Step 4: Re-run tests**

```bash
python manage.py test core.tests.test_physics_kim_reference_widget -v 2
```

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/tests/test_physics_kim_reference_widget.py
git commit -m "feat: add physics KIM reference gating context"
```

---

## Task 3: Create widget include + content fragments

**Files:**
- Create: `core/templates/core/includes/_physics_kim_reference_widget.html`
- Create: `core/templates/core/includes/_physics_kim_reference_content_ege.html`
- Create: `core/templates/core/includes/_physics_kim_reference_content_oge.html`
- Modify: [student_solve_assignment.html](file:///workspace/core/templates/core/student_solve_assignment.html)
- Modify: [student_practice.html](file:///workspace/core/templates/core/student_practice.html)

- [ ] **Step 1: Implement widget HTML (FAB + modal + tabs)**

Add unique marker:
```html
<button id="physics-kim-fab" ...>?</button>
```

Tabs:
- use `data-tab="constants" | "prefixes" | "units" | "other"`
- simple JS switches visible panel

Modal open/close:
- open on FAB click
- close on overlay click + Escape

- [ ] **Step 2: Add EGE/OGE content fragments**

Hard-code KIM reference in 2 files, structured by tab panels. Example skeleton:

```html
<div data-panel="constants">...KIM таблица...</div>
<div data-panel="prefixes" class="hidden">...</div>
...
```

Keep only KIM content.

- [ ] **Step 3: Include widget in both pages**

In `student_solve_assignment.html` near bottom (before image modal include):
```django
{% include "core/includes/_physics_kim_reference_widget.html" %}
```
Inside widget include, guard:
```django
{% if physics_kim_ref_enabled %}
...
{% endif %}
```

Same include in `student_practice.html`.

- [ ] **Step 4: Run tests**

```bash
python manage.py test core.tests.test_physics_kim_reference_widget -v 2
```

- [ ] **Step 5: Commit**

```bash
git add core/templates/core/includes/_physics_kim_reference_widget.html \
       core/templates/core/includes/_physics_kim_reference_content_ege.html \
       core/templates/core/includes/_physics_kim_reference_content_oge.html \
       core/templates/core/student_solve_assignment.html \
       core/templates/core/student_practice.html
git commit -m "feat: add physics KIM reference widget"
```

---

## Self-Review Checklist

- [ ] Widget appears only for Physics EGE/OGE and nowhere else
- [ ] FAB does not block existing critical buttons (upload/finish); keep bottom-right with safe margin
- [ ] Modal scroll works on mobile
- [ ] Escape and overlay click close modal
- [ ] Content is strictly KIM reference (no extra formulas)

