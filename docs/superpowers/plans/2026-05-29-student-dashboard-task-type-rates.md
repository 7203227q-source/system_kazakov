# Student Dashboard Task-Type Solve Rates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить на дашборд ученика блок “Решаемость по номерам” (как у репетитора), фильтруя по выбранному предмету и выбранному `exam_format` в профиле ученика.

**Architecture:** Переиспользовать существующую логику `task_type_rates` из `tutor_dashboard`, вынести расчёт в `core/dashboard_analytics.py` и подключить к `student_dashboard`. UI — плитки с раскраской по проценту (rate) и отображением `correct/total`.

**Tech Stack:** Django ORM, Chart.js (для существующих графиков), Django TestCase (`python manage.py test`).

---

## File Map

- Modify: `/workspace/core/dashboard_analytics.py` — добавить helper `build_task_type_rates(...)`.
- Modify: `/workspace/core/views.py` — `student_dashboard`: добавить `task_type_rates` и `active_exam_format_label` в контекст.
- Modify: `/workspace/core/templates/core/student_dashboard.html` — добавить блок плиток “Решаемость по номерам” и JS-раскраску как в `tutor_dashboard.html`.
- Create: `/workspace/core/tests/test_student_dashboard_task_type_rates.py` — регресс-тесты.

---

## Behavior Spec (точные требования)

### Фильтры данных

- Предмет: `active_subject_id` (GET `subject_id`) — как уже используется в `student_dashboard`.
- Формат: только `active_profile.exam_format` (вариант A).
  - Если `active_profile` отсутствует или `active_profile.exam_format` не выбран, то:
    - `task_type_rates = []`
    - `active_exam_format_label = None`
    - В шаблоне показывается сообщение “Выберите формат экзамена в настройках обучения”.

### Логика “последняя попытка”

- Для каждой `task_id` берётся последняя попытка (последний `Submission.created_at`) среди попыток ученика, прошедших фильтры.
- Учитываются только попытки, где есть результат:
  - `is_correct is not null` или `tutor_primary_score is not null` или `primary_score is not null` или `score is not null`

### Подсчёт earned/max/frac

- `max_points`:
  - если `task.exam_points > 0`: `task.exam_points`
  - иначе `task.task_type.max_points`
  - иначе 1
- `earned`:
  - если `is_correct=True`: `earned = max_points`
  - иначе `earned = tutor_primary_score` или `primary_score` или `score` или 0
- `frac = clamp(earned / max_points, 0..1)`

### Decay (затухание)

- Half-life: 14 дней.
- Вес последней попытки: `weight = 0.5 ** (age_days / 14.0)`, где `age_days = (today - last_created_at.date()).days`.
- Для `rate` агрегируем:
  - `wt += weight`
  - `ws += weight * frac`
  - `rate = (ws / wt) * 100`, если `wt > 0`, иначе `None`
- `correct/total` в плитке не должны быть decay-взвешенными:
  - `total = sum(max_points)` по последним попыткам
  - `correct = sum(earned)` по последним попыткам

### Какие номера показываем

- Ровно те номера, которые существуют в `TaskType` для `active_exam_format`:
  - `numbers = TaskType.objects.filter(exam_format=active_exam_format).values_list("number", flat=True).order_by("number")`
- Для номера без данных (нет попыток в агрегате) `rate=None`, `correct=0`, `total=0`.

---

## Task 1: Add Failing Tests (TDD)

**Files:**
- Create: `/workspace/core/tests/test_student_dashboard_task_type_rates.py`

- [ ] **Step 1: Write failing tests**

```python
import json
from datetime import datetime, time

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, StudentSubjectProfile, Subject, Submission, Task, TaskType, Topic, User


class StudentDashboardTaskTypeRatesTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pw", role="student")
        self.client.force_login(self.student)

        self.subject = Subject.objects.create(name="Физика")
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")
        self.ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ физика", year=2026, is_active=True)

        self.tt1 = TaskType.objects.create(exam_format=self.ef, number=1, name="№1", max_points=1, is_extended_answer=False)
        self.tt2 = TaskType.objects.create(exam_format=self.ef, number=2, name="№2", max_points=2, is_extended_answer=False)

        StudentSubjectProfile.objects.create(student=self.student, subject=self.subject, exam_format=self.ef, xp=0)

        self.t1 = Task.objects.create(topic=self.topic, task_type=self.tt1, correct_answer="1", exam_points=1)
        self.t2 = Task.objects.create(topic=self.topic, task_type=self.tt2, correct_answer="12", exam_points=0)

    def test_dashboard_includes_task_type_rates_for_active_subject_and_exam_format(self):
        tz = timezone.get_current_timezone()
        created_at = timezone.make_aware(datetime.combine(timezone.localdate(), time(12, 0)), tz)

        s1 = Submission.objects.create(student=self.student, task=self.t1, is_correct=True)
        Submission.objects.filter(id=s1.id).update(created_at=created_at)

        s2 = Submission.objects.create(student=self.student, task=self.t2, is_correct=False, score=1)
        Submission.objects.filter(id=s2.id).update(created_at=created_at)

        res = self.client.get(reverse("student_dashboard"), {"subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)

        rates = res.context.get("task_type_rates")
        self.assertTrue(isinstance(rates, list))
        self.assertEqual([r["number"] for r in rates], [1, 2])

        r1 = next(r for r in rates if r["number"] == 1)
        self.assertEqual(int(r1["total"]), 1)
        self.assertEqual(int(r1["correct"]), 1)
        self.assertEqual(int(round(float(r1["rate"]))), 100)

        r2 = next(r for r in rates if r["number"] == 2)
        self.assertEqual(int(r2["total"]), 2)
        self.assertEqual(int(r2["correct"]), 1)
        self.assertEqual(int(round(float(r2["rate"]))), 50)

    def test_dashboard_shows_no_tiles_when_exam_format_not_selected(self):
        StudentSubjectProfile.objects.filter(student=self.student, subject=self.subject).update(exam_format=None)
        res = self.client.get(reverse("student_dashboard"), {"subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context.get("task_type_rates"), [])
        self.assertIsNone(res.context.get("active_exam_format_label"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python manage.py test core.tests.test_student_dashboard_task_type_rates -v 2
```

Expected: FAIL (`task_type_rates`/`active_exam_format_label` отсутствуют в контексте).

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_student_dashboard_task_type_rates.py
git commit -m "test(student): task type rates on dashboard"
```

---

## Task 2: Implement build_task_type_rates Helper

**Files:**
- Modify: `/workspace/core/dashboard_analytics.py`
- Test: `/workspace/core/tests/test_student_dashboard_task_type_rates.py`

- [ ] **Step 1: Add helper**

Add to `core/dashboard_analytics.py`:

```python
from datetime import datetime

from django.db.models import OuterRef, Subquery
from django.utils import timezone

from core.models import Submission, TaskType


def build_task_type_rates(student, *, subject_id: int | None, exam_format, today=None) -> tuple[list[dict], str | None]:
    if not subject_id or not exam_format:
        return ([], None)

    if today is None:
        today = timezone.localdate()

    active_exam_format_label = f"{exam_format.name} {exam_format.year}"

    submissions_base = (
        Submission.objects.filter(student=student, task__topic__subject_id=int(subject_id))
        .filter(task__task_type__exam_format=exam_format)
        .exclude(task__task_type__number__isnull=True)
    )

    scored_filter = (
        models.Q(is_correct__isnull=False)
        | models.Q(tutor_primary_score__isnull=False)
        | models.Q(primary_score__isnull=False)
        | models.Q(score__isnull=False)
    )
    submissions_scored = submissions_base.filter(scored_filter)

    latest_id_subq = (
        submissions_scored.filter(task_id=OuterRef("task_id"))
        .order_by("-created_at", "-id")
        .values("id")[:1]
    )
    latest_rows = (
        submissions_scored.annotate(latest_id=Subquery(latest_id_subq))
        .filter(id=models.F("latest_id"))
        .select_related("task", "task__task_type")
        .values(
            "task__task_type__number",
            "created_at",
            "is_correct",
            "tutor_primary_score",
            "primary_score",
            "score",
            "task__exam_points",
            "task__task_type__max_points",
        )
    )

    half_life_days = 14.0
    agg: dict[int, dict] = {}
    for r in latest_rows:
        n = int(r["task__task_type__number"])
        created_at = r["created_at"]
        age_days = max(0, (today - created_at.date()).days)
        weight = 0.5 ** (float(age_days) / float(half_life_days))

        mp = int(r["task__exam_points"] or 0)
        if mp <= 0:
            mp = int(r["task__task_type__max_points"] or 1)
        mp = max(1, int(mp))

        if bool(r["is_correct"]):
            earned = float(mp)
        else:
            v = r["tutor_primary_score"]
            if v is None:
                v = r["primary_score"]
            if v is None:
                v = r["score"]
            earned = float(v or 0)

        frac = earned / float(mp) if mp > 0 else 0.0
        frac = max(0.0, min(1.0, float(frac)))

        a = agg.setdefault(n, {"wt": 0.0, "ws": 0.0, "total": 0.0, "correct": 0.0})
        a["wt"] += float(weight)
        a["ws"] += float(weight) * float(frac)
        a["total"] += float(mp)
        a["correct"] += float(earned)

    numbers = list(
        TaskType.objects.filter(exam_format=exam_format).values_list("number", flat=True).order_by("number")
    )
    numbers = [int(n) for n in numbers if n is not None]

    task_type_name_map = {int(t.number): (t.name or "") for t in TaskType.objects.filter(exam_format=exam_format)}

    task_type_rates: list[dict] = []
    for n in numbers:
        a = agg.get(int(n))
        if not a or float(a.get("wt") or 0.0) <= 0:
            task_type_rates.append({"number": n, "name": task_type_name_map.get(n, ""), "rate": None, "total": 0, "correct": 0})
            continue
        rate = (float(a["ws"]) / float(a["wt"]) * 100.0) if float(a["wt"]) > 0 else None
        task_type_rates.append(
            {
                "number": n,
                "name": task_type_name_map.get(n, ""),
                "rate": rate,
                "total": int(round(float(a["total"]))),
                "correct": int(round(float(a["correct"]))),
            }
        )

    return (task_type_rates, active_exam_format_label)
```

- [ ] **Step 2: Run tests**

Run:

```bash
python manage.py test core.tests.test_student_dashboard_task_type_rates -v 2
```

Expected: still FAIL until wired into the view.

- [ ] **Step 3: Commit**

```bash
git add core/dashboard_analytics.py
git commit -m "feat(analytics): compute task type solve rates"
```

---

## Task 3: Wire Into student_dashboard Context

**Files:**
- Modify: `/workspace/core/views.py`
- Test: `/workspace/core/tests/test_student_dashboard_task_type_rates.py`

- [ ] **Step 1: Add context fields**

In `student_dashboard` after `active_profile` is computed:

```python
from core.dashboard_analytics import build_task_type_rates

task_type_rates, active_exam_format_label = build_task_type_rates(
    request.user,
    subject_id=int(active_subject_id) if active_subject_id else None,
    exam_format=getattr(active_profile, "exam_format", None) if active_profile else None,
)
```

Add to render context:
- `task_type_rates`
- `active_exam_format_label`

- [ ] **Step 2: Run tests**

Run:

```bash
python manage.py test core.tests.test_student_dashboard_task_type_rates -v 2
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add core/views.py
git commit -m "feat(student): add task type rates to dashboard context"
```

---

## Task 4: Render Task-Type Tiles in Student Dashboard

**Files:**
- Modify: `/workspace/core/templates/core/student_dashboard.html`

- [ ] **Step 1: Add block in template**

Add a section near existing weekly chart and summary:

- If `task_type_rates` not empty:
  - render grid of tiles, same markup style as tutor dashboard
- Else:
  - render message and link to learning settings:
    - `href="{% url 'student_learning_settings' %}?subject_id={{ active_subject_id }}"`

Use the same structure as tutor dashboard tiles (`task-type-tile`, `data-rate`).

- [ ] **Step 2: Add tile-coloring JS**

Copy the tile-coloring JS from tutor dashboard (the `querySelectorAll('.task-type-tile')` loop) into the student dashboard script section (reuse the same class name).

- [ ] **Step 3: Run tests**

Run:

```bash
python manage.py test core.tests.test_student_dashboard_task_type_rates -v 2
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/student_dashboard.html
git commit -m "feat(student): render task type rates tiles on dashboard"
```

---

## Plan Self-Review

- Spec coverage: реализованы фильтры subject+exam_format, last-attempt, decay, список номеров формата, и fallback-сообщение.
- Placeholder scan: нет TODO/TBD, все шаги и команды конкретны.
- Type consistency: имена `task_type_rates` / `active_exam_format_label` совпадают во view, тестах и шаблоне.

