# Physics KIM Reference (FAB + Modal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a floating “?” button that opens a KIM-only Physics reference in a modal, always available while solving both an assignment variant and practice.

**Architecture:** Gated widget include (FAB + modal + tabs + tiny vanilla JS) + two content fragments (ЕГЭ/ОГЭ). Views compute `physics_kim_ref_enabled/kind` and templates include the widget at the end of `<body>`.

**Tech Stack:** Django templates, Tailwind utility classes, minimal vanilla JS, Django tests via `python manage.py test`.

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

**Spec**
- [physics-kim-reference-design.md](file:///workspace/docs/superpowers/specs/2026-05-21-physics-kim-reference-design.md)

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

- [ ] **Step 1: Create test file**

Create [test_physics_kim_reference_widget.py](file:///workspace/core/tests/test_physics_kim_reference_widget.py) with:

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, StudentSubjectProfile, Task, TaskType, Topic, User


class PhysicsKimReferenceWidgetTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")

    def _mk_task(self, *, subject_name: str, exam_format_name: str):
        subj = Subject.objects.create(name=subject_name)
        ef = ExamFormat.objects.create(subject=subj, name=exam_format_name, year=2026, is_active=True)
        topic = Topic.objects.create(subject=subj, name="T")
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1)
        task = Task.objects.create(
            topic=topic,
            task_type=tt,
            correct_answer="1",
            difficulty=10,
            exam_points=1,
        )
        return subj, ef, task

    def test_assignment_page_shows_widget_for_physics_ege(self):
        subj, ef, task = self._mk_task(subject_name="Физика", exam_format_name="ЕГЭ физика")
        StudentSubjectProfile.objects.create(student=self.student, subject=subj, exam_format=ef)

        a = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="A",
            is_draft=False,
            is_completed=False,
            exam_format=ef,
        )
        a.tasks.add(task)

        self.client.login(username="s", password="pass")
        r = self.client.get(reverse("student_solve_assignment", args=[a.id]))
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="physics-kim-fab"', r.content.decode("utf-8"))

    def test_assignment_page_does_not_show_widget_for_non_physics(self):
        subj, ef, task = self._mk_task(subject_name="Математика", exam_format_name="ЕГЭ математика")
        StudentSubjectProfile.objects.create(student=self.student, subject=subj, exam_format=ef)

        a = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="A",
            is_draft=False,
            is_completed=False,
            exam_format=ef,
        )
        a.tasks.add(task)

        self.client.login(username="s", password="pass")
        r = self.client.get(reverse("student_solve_assignment", args=[a.id]))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('id="physics-kim-fab"', r.content.decode("utf-8"))

    def test_practice_page_shows_widget_for_physics_oge(self):
        subj, ef, task = self._mk_task(subject_name="Физика", exam_format_name="ОГЭ физика")
        StudentSubjectProfile.objects.create(student=self.student, subject=subj, exam_format=ef)

        self.client.login(username="s", password="pass")
        r = self.client.get(reverse("student_practice") + f"?subject_id={subj.id}")
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="physics-kim-fab"', r.content.decode("utf-8"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python manage.py test core.tests.test_physics_kim_reference_widget -v 2
```

Expected: FAIL (widget marker not present yet).

---

## Task 2: Add gating context in views (minimal code)

**Files:**
- Modify: [views.py](file:///workspace/core/views.py)

- [ ] **Step 1: Add helper for deciding (subject_name, exam_format_name)**

In [views.py](file:///workspace/core/views.py), add near `student_practice` and `student_solve_assignment` (close to the functions) a helper:

```python
def _physics_kim_ref_flags(*, subject_name: str, exam_format_name: str):
    s = (subject_name or "").strip().lower()
    e = (exam_format_name or "").strip().lower()
    is_physics = "физ" in s
    is_ege = "егэ" in e
    is_oge = "огэ" in e
    enabled = bool(is_physics and (is_ege or is_oge))
    kind = "ege" if enabled and is_ege else ("oge" if enabled and is_oge else "")
    return enabled, kind
```

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

- [ ] **Step 5: Commit (optional)**

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

Create [\_physics_kim_reference_widget.html](file:///workspace/core/templates/core/includes/_physics_kim_reference_widget.html) with:

```html
{% if physics_kim_ref_enabled %}
<div id="physics-kim-ref-root" class="fixed z-[60] bottom-5 right-5">
  <button
    id="physics-kim-fab"
    type="button"
    class="w-14 h-14 rounded-full bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white shadow-lg flex items-center justify-center text-2xl font-bold"
    aria-label="Справочные данные КИМ"
  >
    ?
  </button>
</div>

<div id="physics-kim-modal-overlay" class="hidden fixed inset-0 z-[70] bg-black/50"></div>
<div id="physics-kim-modal" class="hidden fixed inset-0 z-[80] flex items-end sm:items-center justify-center p-0 sm:p-6">
  <div class="bg-white w-full sm:max-w-3xl sm:rounded-2xl rounded-t-2xl shadow-xl max-h-[85dvh] flex flex-col overflow-hidden">
    <div class="px-4 sm:px-6 py-4 border-b border-gray-200 flex items-center justify-between gap-3">
      <div class="font-bold text-gray-800">Справочные данные (КИМ)</div>
      <button type="button" id="physics-kim-close" class="text-gray-500 hover:text-gray-800 px-2 py-1 rounded-lg">
        <span class="sr-only">Закрыть</span>
        <i class="fas fa-times"></i>
      </button>
    </div>

    <div class="px-4 sm:px-6 pt-3">
      <div class="flex flex-wrap gap-2">
        <button type="button" class="physics-kim-tab px-3 py-2 rounded-lg text-xs font-bold bg-indigo-600 text-white" data-tab="constants">Константы</button>
        <button type="button" class="physics-kim-tab px-3 py-2 rounded-lg text-xs font-bold bg-gray-100 text-gray-700 hover:bg-gray-200" data-tab="prefixes">Приставки</button>
        <button type="button" class="physics-kim-tab px-3 py-2 rounded-lg text-xs font-bold bg-gray-100 text-gray-700 hover:bg-gray-200" data-tab="units">Единицы</button>
        <button type="button" class="physics-kim-tab px-3 py-2 rounded-lg text-xs font-bold bg-gray-100 text-gray-700 hover:bg-gray-200" data-tab="other">Прочее</button>
      </div>
    </div>

    <div class="px-4 sm:px-6 py-4 overflow-y-auto">
      {% if physics_kim_ref_kind == "ege" %}
        {% include "core/includes/_physics_kim_reference_content_ege.html" %}
      {% elif physics_kim_ref_kind == "oge" %}
        {% include "core/includes/_physics_kim_reference_content_oge.html" %}
      {% endif %}
    </div>
  </div>
</div>

<script>
  (function () {
    const fab = document.getElementById("physics-kim-fab");
    const overlay = document.getElementById("physics-kim-modal-overlay");
    const modal = document.getElementById("physics-kim-modal");
    const closeBtn = document.getElementById("physics-kim-close");
    if (!fab || !overlay || !modal || !closeBtn) return;

    const tabs = Array.from(document.querySelectorAll(".physics-kim-tab"));
    const panels = Array.from(document.querySelectorAll("[data-panel]"));

    function setOpen(isOpen) {
      overlay.classList.toggle("hidden", !isOpen);
      modal.classList.toggle("hidden", !isOpen);
      document.body.classList.toggle("overflow-hidden", isOpen);
    }

    function setActiveTab(key) {
      tabs.forEach((t) => {
        const active = (t.getAttribute("data-tab") || "") === key;
        t.classList.toggle("bg-indigo-600", active);
        t.classList.toggle("text-white", active);
        t.classList.toggle("bg-gray-100", !active);
        t.classList.toggle("text-gray-700", !active);
      });
      panels.forEach((p) => {
        const show = (p.getAttribute("data-panel") || "") === key;
        p.classList.toggle("hidden", !show);
      });
    }

    fab.addEventListener("click", () => { setOpen(true); });
    closeBtn.addEventListener("click", () => { setOpen(false); });
    overlay.addEventListener("click", () => { setOpen(false); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setOpen(false);
    });
    tabs.forEach((t) => t.addEventListener("click", () => setActiveTab(t.getAttribute("data-tab") || "constants")));

    setActiveTab("constants");
  })();
</script>
{% endif %}
```

- [ ] **Step 2: Add EGE/OGE content fragments**

Hard-code KIM reference in 2 files, structured by tab panels.

```html
<div data-panel="constants">...</div>
<div data-panel="prefixes" class="hidden">...</div>
<div data-panel="units" class="hidden">...</div>
<div data-panel="other" class="hidden">...</div>
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

- [ ] **Step 5: Commit (optional)**

```bash
git add core/templates/core/includes/_physics_kim_reference_widget.html \
       core/templates/core/includes/_physics_kim_reference_content_ege.html \
       core/templates/core/includes/_physics_kim_reference_content_oge.html \
       core/templates/core/student_solve_assignment.html \
       core/templates/core/student_practice.html
git commit -m "feat: add physics KIM reference widget"
```

---

## Task 4: Fill EGE reference content (strictly from KIM)

**Files:**
- Create: [\_physics_kim_reference_content_ege.html](file:///workspace/core/templates/core/includes/_physics_kim_reference_content_ege.html)

- [ ] **Step 1: Add panels markup**

Create file with:

```html
<div data-panel="constants">
  <div class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Константы</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2 font-bold">число π</td><td class="p-2">π = 3,14</td></tr>
        <tr><td class="p-2 font-bold">ускорение свободного падения на Земле</td><td class="p-2">g = 10 м/с²</td></tr>
        <tr><td class="p-2 font-bold">гравитационная постоянная</td><td class="p-2">G = 6,7·10⁻¹¹ Н·м²/кг²</td></tr>
        <tr><td class="p-2 font-bold">универсальная газовая постоянная</td><td class="p-2">R = 8,31 Дж/(моль·К)</td></tr>
        <tr><td class="p-2 font-bold">постоянная Больцмана</td><td class="p-2">k = 1,38·10⁻²³ Дж/К</td></tr>
        <tr><td class="p-2 font-bold">постоянная Авогадро</td><td class="p-2">N<sub>А</sub> = 6·10²³ моль⁻¹</td></tr>
        <tr><td class="p-2 font-bold">скорость света в вакууме</td><td class="p-2">c = 3·10⁸ м/с</td></tr>
        <tr><td class="p-2 font-bold">коэффициент пропорциональности в законе Кулона</td><td class="p-2">k = 1/(4π ε<sub>0</sub>) = 9·10⁹ Н·м²/Кл²</td></tr>
        <tr><td class="p-2 font-bold">электрическая постоянная</td><td class="p-2">ε<sub>0</sub> = 8,85·10⁻¹² Ф/м</td></tr>
        <tr><td class="p-2 font-bold">модуль заряда электрона (элементарный электрический заряд)</td><td class="p-2">e = 1,6·10⁻¹⁹ Кл</td></tr>
        <tr><td class="p-2 font-bold">постоянная Планка</td><td class="p-2">h = 6,6·10⁻³⁴ Дж·с</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div data-panel="prefixes" class="hidden">
  <div class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Десятичные приставки</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <thead class="bg-gray-50">
        <tr>
          <th class="p-2 text-left">Наименование</th>
          <th class="p-2 text-left">Обозначение</th>
          <th class="p-2 text-left">Множитель</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2">гига</td><td class="p-2">Г</td><td class="p-2">10⁹</td></tr>
        <tr><td class="p-2">мега</td><td class="p-2">М</td><td class="p-2">10⁶</td></tr>
        <tr><td class="p-2">кило</td><td class="p-2">к</td><td class="p-2">10³</td></tr>
        <tr><td class="p-2">гекто</td><td class="p-2">г</td><td class="p-2">10²</td></tr>
        <tr><td class="p-2">деци</td><td class="p-2">д</td><td class="p-2">10⁻¹</td></tr>
        <tr><td class="p-2">санти</td><td class="p-2">с</td><td class="p-2">10⁻²</td></tr>
        <tr><td class="p-2">милли</td><td class="p-2">м</td><td class="p-2">10⁻³</td></tr>
        <tr><td class="p-2">микро</td><td class="p-2">мк</td><td class="p-2">10⁻⁶</td></tr>
        <tr><td class="p-2">нано</td><td class="p-2">н</td><td class="p-2">10⁻⁹</td></tr>
        <tr><td class="p-2">пико</td><td class="p-2">п</td><td class="p-2">10⁻¹²</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div data-panel="units" class="hidden">
  <div class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Соотношения между единицами / массы частиц</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2 font-bold">температура</td><td class="p-2">0 К = −273 °С</td></tr>
        <tr><td class="p-2 font-bold">атомная единица массы</td><td class="p-2">1 а.е.м. = 1,66·10⁻²⁷ кг</td></tr>
        <tr><td class="p-2 font-bold">эквивалент энергии</td><td class="p-2">1 а.е.м. эквивалентна 931,5 МэВ</td></tr>
        <tr><td class="p-2 font-bold">электронвольт</td><td class="p-2">1 эВ = 1,6·10⁻¹⁹ Дж</td></tr>
      </tbody>
    </table>
  </div>

  <div class="mt-4 text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Масса частиц</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2 font-bold">электрона</td><td class="p-2">9,1·10⁻³¹ кг ≈ 5,5·10⁻⁴ а.е.м.</td></tr>
        <tr><td class="p-2 font-bold">протона</td><td class="p-2">1,673·10⁻²⁷ кг ≈ 1,007 а.е.м.</td></tr>
        <tr><td class="p-2 font-bold">нейтрона</td><td class="p-2">1,675·10⁻²⁷ кг ≈ 1,008 а.е.м.</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div data-panel="other" class="hidden">
  <div class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Табличные данные</div>

  <div class="mt-2 text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Плотность</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2 font-bold">подсолнечного масла</td><td class="p-2">900 кг/м³</td></tr>
        <tr><td class="p-2 font-bold">воды</td><td class="p-2">1000 кг/м³</td></tr>
        <tr><td class="p-2 font-bold">древесины (сосна)</td><td class="p-2">400 кг/м³</td></tr>
        <tr><td class="p-2 font-bold">керосина</td><td class="p-2">800 кг/м³</td></tr>
        <tr><td class="p-2 font-bold">алюминия</td><td class="p-2">2700 кг/м³</td></tr>
        <tr><td class="p-2 font-bold">железа</td><td class="p-2">7800 кг/м³</td></tr>
        <tr><td class="p-2 font-bold">ртути</td><td class="p-2">13 600 кг/м³</td></tr>
      </tbody>
    </table>
  </div>

  <div class="mt-4 text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Удельная теплоёмкость</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2 font-bold">воды</td><td class="p-2">4,2·10³ Дж/(кг·К)</td></tr>
        <tr><td class="p-2 font-bold">льда</td><td class="p-2">2,1·10³ Дж/(кг·К)</td></tr>
        <tr><td class="p-2 font-bold">железа</td><td class="p-2">460 Дж/(кг·К)</td></tr>
        <tr><td class="p-2 font-bold">свинца</td><td class="p-2">130 Дж/(кг·К)</td></tr>
        <tr><td class="p-2 font-bold">алюминия</td><td class="p-2">900 Дж/(кг·К)</td></tr>
        <tr><td class="p-2 font-bold">меди</td><td class="p-2">380 Дж/(кг·К)</td></tr>
        <tr><td class="p-2 font-bold">чугуна</td><td class="p-2">500 Дж/(кг·К)</td></tr>
      </tbody>
    </table>
  </div>

  <div class="mt-4 text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Удельная теплота</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2 font-bold">парообразования воды</td><td class="p-2">2,3·10⁶ Дж/кг</td></tr>
        <tr><td class="p-2 font-bold">плавления свинца</td><td class="p-2">2,5·10⁴ Дж/кг</td></tr>
        <tr><td class="p-2 font-bold">плавления льда</td><td class="p-2">3,3·10⁵ Дж/кг</td></tr>
      </tbody>
    </table>
  </div>

  <div class="mt-4 text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Нормальные условия</div>
  <div class="text-sm text-gray-700">давление 10⁵ Па, температура 0 °С</div>

  <div class="mt-4 text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Молярная масса</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2 font-bold">азота</td><td class="p-2">28·10⁻³ кг/моль</td><td class="p-2 font-bold">гелия</td><td class="p-2">4·10⁻³ кг/моль</td></tr>
        <tr><td class="p-2 font-bold">аргона</td><td class="p-2">40·10⁻³ кг/моль</td><td class="p-2 font-bold">кислорода</td><td class="p-2">32·10⁻³ кг/моль</td></tr>
        <tr><td class="p-2 font-bold">водорода</td><td class="p-2">2·10⁻³ кг/моль</td><td class="p-2 font-bold">лития</td><td class="p-2">6·10⁻³ кг/моль</td></tr>
        <tr><td class="p-2 font-bold">воздуха</td><td class="p-2">29·10⁻³ кг/моль</td><td class="p-2 font-bold">неона</td><td class="p-2">20·10⁻³ кг/моль</td></tr>
        <tr><td class="p-2 font-bold">воды</td><td class="p-2">18·10⁻³ кг/моль</td><td class="p-2 font-bold">углекислого газа</td><td class="p-2">44·10⁻³ кг/моль</td></tr>
      </tbody>
    </table>
  </div>
</div>
```

---

## Task 5: Fill OGE reference content (strictly from KIM)

**Files:**
- Create: [\_physics_kim_reference_content_oge.html](file:///workspace/core/templates/core/includes/_physics_kim_reference_content_oge.html)

- [ ] **Step 1: Add panels markup**

Create file with:

```html
<div data-panel="constants">
  <div class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Константы</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2 font-bold">ускорение свободного падения на Земле</td><td class="p-2">g = 10 м/с²</td></tr>
        <tr><td class="p-2 font-bold">гравитационная постоянная</td><td class="p-2">G = 6,7·10⁻¹¹ Н·м²/кг²</td></tr>
        <tr><td class="p-2 font-bold">скорость света в вакууме</td><td class="p-2">c = 3·10⁸ м/с</td></tr>
        <tr><td class="p-2 font-bold">элементарный электрический заряд</td><td class="p-2">e = 1,6·10⁻¹⁹ Кл</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div data-panel="prefixes" class="hidden">
  <div class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Десятичные приставки</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <thead class="bg-gray-50">
        <tr>
          <th class="p-2 text-left">Наименование</th>
          <th class="p-2 text-left">Обозначение</th>
          <th class="p-2 text-left">Множитель</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2">гига</td><td class="p-2">Г</td><td class="p-2">10⁹</td></tr>
        <tr><td class="p-2">мега</td><td class="p-2">М</td><td class="p-2">10⁶</td></tr>
        <tr><td class="p-2">кило</td><td class="p-2">к</td><td class="p-2">10³</td></tr>
        <tr><td class="p-2">гекто</td><td class="p-2">г</td><td class="p-2">10²</td></tr>
        <tr><td class="p-2">санти</td><td class="p-2">с</td><td class="p-2">10⁻²</td></tr>
        <tr><td class="p-2">милли</td><td class="p-2">м</td><td class="p-2">10⁻³</td></tr>
        <tr><td class="p-2">микро</td><td class="p-2">мк</td><td class="p-2">10⁻⁶</td></tr>
        <tr><td class="p-2">нано</td><td class="p-2">н</td><td class="p-2">10⁻⁹</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div data-panel="units" class="hidden">
  <div class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Нормальные условия</div>
  <div class="text-sm text-gray-700">давление 10⁵ Па, температура 0 °С</div>

  <div class="mt-4 text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Температуры</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <thead class="bg-gray-50">
        <tr><th class="p-2 text-left">Температура плавления</th><th class="p-2 text-left">Значение</th><th class="p-2 text-left">Температура кипения</th><th class="p-2 text-left">Значение</th></tr>
      </thead>
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2">свинца</td><td class="p-2">327 °С</td><td class="p-2">воды</td><td class="p-2">100 °С</td></tr>
        <tr><td class="p-2">олова</td><td class="p-2">232 °С</td><td class="p-2">спирта</td><td class="p-2">78 °С</td></tr>
        <tr><td class="p-2">льда</td><td class="p-2">0 °С</td><td class="p-2"></td><td class="p-2"></td></tr>
      </tbody>
    </table>
  </div>

  <div class="mt-4 text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Удельное электрическое сопротивление, Ом·мм²/м (при 20 °С)</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2 font-bold">серебро</td><td class="p-2">0,016</td><td class="p-2 font-bold">никелин</td><td class="p-2">0,4</td></tr>
        <tr><td class="p-2 font-bold">медь</td><td class="p-2">0,017</td><td class="p-2 font-bold">нихром (сплав)</td><td class="p-2">1,1</td></tr>
        <tr><td class="p-2 font-bold">алюминий</td><td class="p-2">0,028</td><td class="p-2 font-bold">фехраль</td><td class="p-2">1,2</td></tr>
        <tr><td class="p-2 font-bold">железо</td><td class="p-2">0,10</td><td class="p-2 font-bold"></td><td class="p-2"></td></tr>
      </tbody>
    </table>
  </div>
</div>

<div data-panel="other" class="hidden">
  <div class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Плотность</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <thead class="bg-gray-50">
        <tr><th class="p-2 text-left">Жидкости</th><th class="p-2 text-left">Значение</th><th class="p-2 text-left">Твёрдые тела</th><th class="p-2 text-left">Значение</th></tr>
      </thead>
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2">бензин</td><td class="p-2">710 кг/м³</td><td class="p-2">древесина (сосна)</td><td class="p-2">400 кг/м³</td></tr>
        <tr><td class="p-2">спирт</td><td class="p-2">800 кг/м³</td><td class="p-2">парафин</td><td class="p-2">900 кг/м³</td></tr>
        <tr><td class="p-2">керосин</td><td class="p-2">800 кг/м³</td><td class="p-2">лёд</td><td class="p-2">900 кг/м³</td></tr>
        <tr><td class="p-2">масло машинное</td><td class="p-2">900 кг/м³</td><td class="p-2">алюминий</td><td class="p-2">2700 кг/м³</td></tr>
        <tr><td class="p-2">вода</td><td class="p-2">1000 кг/м³</td><td class="p-2">мрамор</td><td class="p-2">2700 кг/м³</td></tr>
        <tr><td class="p-2">молоко цельное</td><td class="p-2">1030 кг/м³</td><td class="p-2">цинк</td><td class="p-2">7100 кг/м³</td></tr>
        <tr><td class="p-2">вода морская</td><td class="p-2">1030 кг/м³</td><td class="p-2">сталь, железо</td><td class="p-2">7800 кг/м³</td></tr>
        <tr><td class="p-2">глицерин</td><td class="p-2">1260 кг/м³</td><td class="p-2">медь</td><td class="p-2">8900 кг/м³</td></tr>
        <tr><td class="p-2">ртуть</td><td class="p-2">13 600 кг/м³</td><td class="p-2">свинец</td><td class="p-2">11 350 кг/м³</td></tr>
      </tbody>
    </table>
  </div>

  <div class="mt-4 text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Удельная теплоёмкость / теплоты</div>
  <div class="overflow-x-auto">
    <table class="min-w-full text-sm border border-gray-200">
      <thead class="bg-gray-50">
        <tr><th class="p-2 text-left">Удельная теплоёмкость</th><th class="p-2 text-left">Значение</th><th class="p-2 text-left">Удельная теплота</th><th class="p-2 text-left">Значение</th></tr>
      </thead>
      <tbody class="divide-y divide-gray-200">
        <tr><td class="p-2">воды</td><td class="p-2">4200 Дж/(кг·°С)</td><td class="p-2">парообразования воды</td><td class="p-2">2,3·10⁶ Дж/кг</td></tr>
        <tr><td class="p-2">спирта</td><td class="p-2">2400 Дж/(кг·°С)</td><td class="p-2">парообразования спирта</td><td class="p-2">9,0·10⁵ Дж/кг</td></tr>
        <tr><td class="p-2">льда</td><td class="p-2">2100 Дж/(кг·°С)</td><td class="p-2">плавления свинца</td><td class="p-2">2,5·10⁴ Дж/кг</td></tr>
        <tr><td class="p-2">алюминия</td><td class="p-2">920 Дж/(кг·°С)</td><td class="p-2">плавления стали</td><td class="p-2">7,8·10⁴ Дж/кг</td></tr>
        <tr><td class="p-2">стали</td><td class="p-2">500 Дж/(кг·°С)</td><td class="p-2">плавления олова</td><td class="p-2">5,9·10⁴ Дж/кг</td></tr>
        <tr><td class="p-2">цинка</td><td class="p-2">400 Дж/(кг·°С)</td><td class="p-2">плавления льда</td><td class="p-2">3,3·10⁵ Дж/кг</td></tr>
        <tr><td class="p-2">меди</td><td class="p-2">400 Дж/(кг·°С)</td><td class="p-2">сгорания спирта</td><td class="p-2">2,9·10⁷ Дж/кг</td></tr>
        <tr><td class="p-2">олова</td><td class="p-2">230 Дж/(кг·°С)</td><td class="p-2">сгорания керосина</td><td class="p-2">4,6·10⁷ Дж/кг</td></tr>
        <tr><td class="p-2">свинца</td><td class="p-2">130 Дж/(кг·°С)</td><td class="p-2">сгорания бензина</td><td class="p-2">4,6·10⁷ Дж/кг</td></tr>
        <tr><td class="p-2">бронзы</td><td class="p-2">420 Дж/(кг·°С)</td><td class="p-2"></td><td class="p-2"></td></tr>
      </tbody>
    </table>
  </div>
</div>
```

---

## Self-Review Checklist

- [ ] Widget appears only for Physics EGE/OGE and nowhere else
- [ ] FAB does not block existing critical buttons (upload/finish); keep bottom-right with safe margin
- [ ] Modal scroll works on mobile
- [ ] Escape and overlay click close modal
- [ ] Content is strictly KIM reference (no extra formulas)
