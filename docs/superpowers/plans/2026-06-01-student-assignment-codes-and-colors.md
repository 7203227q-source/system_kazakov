# Student Assignment Codes & Colors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Показать стабильный трёхзначный код варианта (#001…) и детерминированную цветовую метку в интерфейсе ученика (дашборд, решение, мобильная загрузка), чтобы легко сопоставлять варианты при загрузке фото.

**Architecture:** Используем `Assignment.student_seq` как источник кода. При необходимости дозаполняем `student_seq` для старых вариантов. Цветовая метка вычисляется детерминированно от `student_seq` (палитра) и используется одинаково на всех страницах.

**Tech Stack:** Django (views/templates), Django template tags, JSON API + vanilla JS (поллинг), Tailwind CSS.

---

### Task 1: Добавить утилиты для кода/цвета в шаблонах

**Files:**
- Create: [assignment_ui.py](file:///workspace/core/templatetags/assignment_ui.py)

- [ ] **Step 1: Создать template tags с палитрой**

Создать файл `core/templatetags/assignment_ui.py`:

```python
from django import template

register = template.Library()

_PALETTE = [
    ("#EEF2FF", "#4F46E5"),  # indigo
    ("#ECFDF5", "#10B981"),  # emerald
    ("#FFF7ED", "#F97316"),  # orange
    ("#FDF2F8", "#DB2777"),  # pink
    ("#EFF6FF", "#2563EB"),  # blue
    ("#F5F3FF", "#7C3AED"),  # violet
    ("#FFFBEB", "#D97706"),  # amber
    ("#F0FDFA", "#0D9488"),  # teal
]


@register.filter
def assignment_code(student_seq):
    try:
        n = int(student_seq or 0)
    except Exception:
        n = 0
    if n <= 0:
        return ""
    return f"#{n:03d}"


@register.filter
def assignment_color(student_seq):
    try:
        n = int(student_seq or 0)
    except Exception:
        n = 0
    if n <= 0:
        return {"bg": "#E5E7EB", "fg": "#6B7280"}
    bg, fg = _PALETTE[n % len(_PALETTE)]
    return {"bg": bg, "fg": fg}
```

- [ ] **Step 2: Запустить импортный тест (smoke)**

Run:

```bash
python -m py_compile /workspace/core/templatetags/assignment_ui.py
```

Expected: exit code 0

- [ ] **Step 3: Commit**

```bash
git add core/templatetags/assignment_ui.py
git commit -m "feat: add assignment UI helpers"
```

---

### Task 2: Дозаполнение `student_seq` для существующих вариантов

**Files:**
- Modify: [views.py](file:///workspace/core/views.py)
- Test: [test_student_assignment_student_seq_backfill.py](file:///workspace/core/tests/test_student_assignment_student_seq_backfill.py)

- [ ] **Step 1: Добавить helper в views.py**

Добавить функцию (рядом со student_dashboard / API, чтобы было видно):

```python
from django.db import transaction


def _ensure_student_assignment_seqs(student):
    if not student or getattr(student, "role", None) != "student":
        return
    missing = list(
        Assignment.objects.filter(student=student, is_deleted=False, student_seq__isnull=True)
        .only("id", "created_at")
        .order_by("created_at", "id")
    )
    if not missing:
        return
    with transaction.atomic():
        max_seq = (
            Assignment.objects.filter(student=student, student_seq__isnull=False).aggregate(m=models.Max("student_seq")).get("m")
            or 0
        )
        seq = int(max_seq or 0)
        for a in missing:
            seq += 1
            a.student_seq = seq
        Assignment.objects.bulk_update(missing, ["student_seq"])
```

Важно: импорт `transaction` использовать локально (или вверху файла), но не вводить циклические импорты.

- [ ] **Step 2: Включить backfill в student_dashboard**

В начале `student_dashboard()` (после проверки роли) вызвать:

```python
_ensure_student_assignment_seqs(request.user)
```

Файл: [student_dashboard](file:///workspace/core/views.py#L1030)

- [ ] **Step 3: Включить backfill в api_student_pending_assignments**

Сразу после проверки роли студента:

```python
_ensure_student_assignment_seqs(request.user)
```

Файл: [api_student_pending_assignments](file:///workspace/core/views.py#L7209)

- [ ] **Step 4: Включить backfill в student_solve_assignment**

После `assignment = get_object_or_404(...)`:

```python
if assignment.student_seq is None:
    _ensure_student_assignment_seqs(request.user)
    assignment.refresh_from_db(fields=["student_seq"])
```

Файл: [student_solve_assignment](file:///workspace/core/views.py#L1619)

- [ ] **Step 5: Включить backfill в mobile_upload_draft**

После загрузки `submission`:

```python
assignment = getattr(submission, "assignment", None)
if assignment and assignment.student_seq is None:
    _ensure_student_assignment_seqs(submission.student)
```

Файл: [mobile_upload_draft](file:///workspace/core/views.py#L5526)

- [ ] **Step 6: Добавить тест backfill**

Создать `core/tests/test_student_assignment_student_seq_backfill.py`:

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, Subject, User


class StudentAssignmentStudentSeqBackfillTests(TestCase):
    def test_dashboard_backfills_missing_student_seq(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        subj = Subject.objects.create(name="Математика")

        a1 = Assignment.objects.create(tutor=tutor, student=student, title="A1", is_draft=False, is_completed=False)
        a2 = Assignment.objects.create(tutor=tutor, student=student, title="A2", is_draft=False, is_completed=False)
        self.assertIsNone(a1.student_seq)
        self.assertIsNone(a2.student_seq)

        self.client.login(username="s", password="pass")
        r = self.client.get(reverse("student_dashboard"))
        self.assertEqual(r.status_code, 200)

        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.student_seq, 1)
        self.assertEqual(a2.student_seq, 2)
```

- [ ] **Step 7: Run test**

```bash
python /workspace/manage.py test core.tests.test_student_assignment_student_seq_backfill -v 2
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add core/views.py core/tests/test_student_assignment_student_seq_backfill.py
git commit -m "fix: backfill student assignment sequence numbers"
```

---

### Task 3: Всегда задавать `student_seq` при создании вариантов репетитором

**Files:**
- Modify: [tutor_create_assignment](file:///workspace/core/views.py#L3687)
- Test: [test_assignment_title_autogen.py](file:///workspace/core/tests/test_assignment_title_autogen.py)

- [ ] **Step 1: Исправить одиночное создание**

В месте создания `assignment = Assignment.objects.create(...)` (ветка “создаём один черновик”):
- оставить расчёт `seq_num` как сейчас;
- выставлять `student_seq=seq_num` всегда (не зависеть от `title_input`).

Пример:

```python
assignment = Assignment.objects.create(
    tutor=request.user,
    student=student,
    title=_title_for_seq(seq_num, 1),
    kind=kind,
    student_seq=seq_num,
    is_draft=True,
    exam_format=exam_format,
)
```

- [ ] **Step 2: Исправить bulk publish**

В ветке `publish_bulk` уже есть `student_seq=seq_num` — оставить.

- [ ] **Step 3: Добавить тест “student_seq заполняется даже при ручном title”**

В `core/tests/test_assignment_title_autogen.py` добавить тест:

```python
    def test_student_seq_is_set_even_with_manual_title(self):
        self.client.login(username="t", password="pass")
        res = self.client.post(
            reverse("tutor_create_assignment"),
            {
                "student_id": str(self.student.id),
                "exam_format": str(self.ef.id),
                "kind": "homework",
                "title": "Мой вариант",
                f"type_count_{self.task.task_type_id}": "1",
                "subtype_checked_1": "on",
                "subtype_name_1": self.task.subtype_tag or "",
                "subtype_type_1": str(self.task.task_type_id),
            },
        )
        self.assertEqual(res.status_code, 302)
        a = Assignment.objects.latest("id")
        self.assertEqual(a.title, "Мой вариант")
        self.assertEqual(a.student_seq, 1)
```

- [ ] **Step 4: Run test**

```bash
python /workspace/manage.py test core.tests.test_assignment_title_autogen -v 2
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/tests/test_assignment_title_autogen.py
git commit -m "fix: always assign student_seq for new assignments"
```

---

### Task 4: UI — показывать код и цвет на дашборде ученика (и в поллинге)

**Files:**
- Modify: [student_dashboard.html](file:///workspace/core/templates/core/student_dashboard.html)
- Modify: [api_student_pending_assignments](file:///workspace/core/views.py#L7209)
- Test: [test_student_pending_assignments_api.py](file:///workspace/core/tests/test_student_pending_assignments_api.py)

- [ ] **Step 1: Подключить template tags**

В `student_dashboard.html` добавить:

```django
{% load ui_datetime json_extras assignment_ui %}
```

- [ ] **Step 2: Добавить бейдж к карточке варианта (server-render)**

В блоке карточки:
- показать `{{ assignment.student_seq|assignment_code }}`
- добавить маленькую цветную точку на основе `{{ assignment.student_seq|assignment_color }}`:

```django
{% with c=assignment.student_seq|assignment_color %}
  <span class="inline-flex items-center gap-2">
    <span class="w-2.5 h-2.5 rounded-full border border-white shadow-sm" style="background-color: {{ c.bg }};"></span>
    <span class="text-xs font-black" style="color: {{ c.fg }};">{{ assignment.student_seq|assignment_code }}</span>
  </span>
{% endwith %}
```

- [ ] **Step 3: Добавить `student_seq` в API**

В `api_student_pending_assignments` добавить поле:

```python
"student_seq": a.student_seq,
```

- [ ] **Step 4: Обновить JS render в student_dashboard.html**

В `render(assignments)`:
- вычислять код `#XYZ` на фронте:

```js
const code = (a.student_seq ? `#${String(a.student_seq).padStart(3, '0')}` : '');
```

- цвет по той же палитре (дублируем palette в JS):

```js
const palette = [
  ['#EEF2FF', '#4F46E5'],
  ['#ECFDF5', '#10B981'],
  ['#FFF7ED', '#F97316'],
  ['#FDF2F8', '#DB2777'],
  ['#EFF6FF', '#2563EB'],
  ['#F5F3FF', '#7C3AED'],
  ['#FFFBEB', '#D97706'],
  ['#F0FDFA', '#0D9488'],
];
const color = (a.student_seq && palette.length) ? palette[a.student_seq % palette.length] : ['#E5E7EB', '#6B7280'];
```

И добавить в HTML строки, рядом с названием:

```js
${code ? `<span class="inline-flex items-center gap-2">
  <span class="w-2.5 h-2.5 rounded-full border border-white shadow-sm" style="background-color:${color[0]};"></span>
  <span class="text-[11px] font-black" style="color:${color[1]};">${code}</span>
</span>` : ''}
```

- [ ] **Step 5: Обновить тест API**

В `core/tests/test_student_pending_assignments_api.py`:
- проверить наличие `student_seq` в элементах ответа и что backfill присвоил значения:

```python
        items = data.get("assignments", [])
        self.assertTrue("student_seq" in items[0])
        seqs = [x.get("student_seq") for x in items]
        self.assertEqual(seqs, [2, 1])
```

- [ ] **Step 6: Run test**

```bash
python /workspace/manage.py test core.tests.test_student_pending_assignments_api -v 2
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add core/templates/core/student_dashboard.html core/views.py core/tests/test_student_pending_assignments_api.py
git commit -m "feat: show assignment codes and colors in student dashboard"
```

---

### Task 5: UI — показывать код и цвет на странице решения варианта и mobile upload

**Files:**
- Modify: [student_solve_assignment.html](file:///workspace/core/templates/core/student_solve_assignment.html)
- Modify: [mobile_upload.html](file:///workspace/core/templates/core/mobile_upload.html)

- [ ] **Step 1: student_solve_assignment.html**

Подключить template tags:

```django
{% load ui_datetime json_extras assignment_ui %}
```

В заголовке рядом с `{{ assignment.title }}` добавить `#XYZ` + цветную точку (как в dashboard).

- [ ] **Step 2: mobile_upload.html**

Подключить template tags:

```django
{% load assignment_ui %}
```

Вверху добавить блок, если есть `submission.assignment`:
- `Вариант {{ submission.assignment.student_seq|assignment_code }}`
- цветную точку из `assignment_color`.

- [ ] **Step 3: Smoke compile**

```bash
python -m py_compile /workspace/core/views.py
```

Expected: exit code 0

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/student_solve_assignment.html core/templates/core/mobile_upload.html
git commit -m "feat: show assignment code in solve and upload pages"
```

---

## Self-Review Checklist

- [ ] В UI везде виден `#001` и совпадает для одного и того же варианта.
- [ ] Поллинг `/api/student/pending-assignments/` не “сносит” код/цвет при обновлении списка.
- [ ] Для старых вариантов без `student_seq` номер назначается автоматически и стабильно.
- [ ] Нет ошибок при загрузке фото, если `submission.assignment is None` (mobile upload остаётся рабочим).

