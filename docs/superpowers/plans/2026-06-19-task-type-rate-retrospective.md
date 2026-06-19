# Task Type Rate Retrospective Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в карточки «Решаемость по номерам» текущую взвешенную решаемость и ретроспективу этой же метрики на срезах `4/8/16/32/50` дней назад.

**Architecture:** Вся математика живет в `core/dashboard_analytics.py` как общий helper для student и tutor dashboard. Для каждого номера задачи считается текущий snapshot и historical snapshots: метрика на дату `anchor_day`, как если бы система находилась в тот день. В каждом snapshot учитываются только решения, существовавшие к `anchor_day`, и применяется экспоненциальный decay относительно `anchor_day`; вес не показывается в UI.

**Tech Stack:** Django ORM, Django templates, Python, Django TestCase.

---

## Изменяемые файлы (map)

**Modify**
- `/workspace/core/dashboard_analytics.py` — общий расчет current/retrospective solve-rate и shared constants
- `/workspace/core/views.py` — убрать inline-расчет у tutor dashboard, перейти на helper
- `/workspace/core/templates/core/student_dashboard.html` — расширить карточку и показать retrospective values
- `/workspace/core/templates/core/tutor_dashboard.html` — тот же UI для tutor dashboard
- `/workspace/core/tests/test_student_dashboard_task_type_rates.py` — обновить ожидания student dashboard
- `/workspace/core/tests/test_tutor_solve_rate_decay.py` — обновить/добавить проверки tutor dashboard и decay

**Create**
- `/workspace/core/tests/test_task_type_rate_retrospective.py` — focused tests на historical snapshot semantics

---

## Решения, зафиксированные планом

- `half_life_days = 21.0`:
  - стабильнее текущего `14`
  - сохраняет влияние истории
  - не делает метрику слишком нервной
- Срез `N дней назад` считается на дату `today - N`:
  - берем только попытки с effective timestamp `<= anchor_day`
  - по каждой задаче берем последнюю известную на тот момент попытку
  - decay считается относительно `anchor_day`, а не относительно today
- Effective timestamp для scored attempt:
  - `tutor_scored_at`
  - иначе `ai_last_verify_at`
  - иначе `created_at`
- UI показывает:
  - текущий `%`
  - ряд ретроспективных значений `50д 32д 16д 8д 4д`
  - цвет карточки по текущему `%`
  - weight/half-life отдельно не показываются

---

### Task 1: Написать focused tests на semantics retrospective snapshot

**Files:**
- Create: `/workspace/core/tests/test_task_type_rate_retrospective.py`
- Test: `/workspace/core/dashboard_analytics.py`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.dashboard_analytics import build_task_type_rates
from core.models import ExamFormat, StudentSubjectProfile, Subject, Submission, Task, TaskType, Topic, User


class TaskTypeRateRetrospectiveTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pw", role="student")
        self.subject = Subject.objects.create(name="Физика")
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")
        self.exam_format = ExamFormat.objects.create(
            subject=self.subject,
            name="ОГЭ физика",
            year=2026,
            is_active=True,
        )
        StudentSubjectProfile.objects.create(
            student=self.student,
            subject=self.subject,
            exam_format=self.exam_format,
        )
        self.task_type = TaskType.objects.create(
            exam_format=self.exam_format,
            number=1,
            name="№1",
            max_points=1,
        )
        self.task = Task.objects.create(
            topic=self.topic,
            task_type=self.task_type,
            correct_answer="1",
            exam_points=1,
        )

    def test_snapshot_uses_state_known_on_anchor_day(self):
        today = timezone.localdate()
        older_dt = timezone.now() - timedelta(days=20)
        newer_dt = timezone.now() - timedelta(days=2)

        s1 = Submission.objects.create(student=self.student, task=self.task, is_correct=False, score=0)
        Submission.objects.filter(id=s1.id).update(created_at=older_dt)

        s2 = Submission.objects.create(student=self.student, task=self.task, is_correct=True, score=1)
        Submission.objects.filter(id=s2.id).update(created_at=newer_dt)

        rates, _ = build_task_type_rates(
            self.student,
            subject_id=self.subject.id,
            exam_format=self.exam_format,
            today=today,
        )

        tile = next(item for item in rates if int(item["number"]) == 1)
        retro = {int(point["days_ago"]): point["rate"] for point in tile["retrospective"]}

        self.assertEqual(int(round(float(retro[4]))), 0)
        self.assertEqual(int(round(float(tile["rate"]))), 100)

    def test_snapshot_uses_last_attempt_known_by_that_day(self):
        today = timezone.localdate()
        old_dt = timezone.now() - timedelta(days=40)
        mid_dt = timezone.now() - timedelta(days=10)

        s1 = Submission.objects.create(student=self.student, task=self.task, is_correct=True, score=1)
        Submission.objects.filter(id=s1.id).update(created_at=old_dt)

        s2 = Submission.objects.create(student=self.student, task=self.task, is_correct=False, score=0)
        Submission.objects.filter(id=s2.id).update(created_at=mid_dt)

        rates, _ = build_task_type_rates(
            self.student,
            subject_id=self.subject.id,
            exam_format=self.exam_format,
            today=today,
        )

        tile = next(item for item in rates if int(item["number"]) == 1)
        retro = {int(point["days_ago"]): point["rate"] for point in tile["retrospective"]}

        self.assertEqual(int(round(float(retro[32]))), 100)
        self.assertEqual(int(round(float(retro[8]))), 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
python manage.py test core.tests.test_task_type_rate_retrospective -v 1
```
Expected: FAIL because `build_task_type_rates()` does not return `retrospective` and does not build historical snapshots.

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_task_type_rate_retrospective.py
git commit -m "test: cover task type solve-rate retrospective snapshots"
```

---

### Task 2: Реализовать shared retrospective helper в analytics

**Files:**
- Modify: `/workspace/core/dashboard_analytics.py`
- Test: `/workspace/core/tests/test_task_type_rate_retrospective.py`

- [ ] **Step 1: Add shared constants and helper skeleton**

```python
RETROSPECTIVE_WINDOWS_DAYS = (4, 8, 16, 32, 50)
TASK_TYPE_RATE_HALF_LIFE_DAYS = 21.0


def _effective_scored_dt(row):
    return row["tutor_scored_at"] or row["ai_last_verify_at"] or row["created_at"]


def _rate_for_anchor(rows, *, anchor_day):
    agg = {}
    for row in rows:
        dt = _effective_scored_dt(row)
        if not dt or dt.date() > anchor_day:
            continue

        task_id = int(row["task_id"])
        current = agg.get(task_id)
        if current and _effective_scored_dt(current) >= dt:
            continue
        agg[task_id] = row

    by_number = {}
    for row in agg.values():
        number = int(row["task__task_type__number"])
        age_days = max(0, (anchor_day - _effective_scored_dt(row).date()).days)
        weight = 0.5 ** (float(age_days) / float(TASK_TYPE_RATE_HALF_LIFE_DAYS))

        mp = int(row["task__exam_points"] or row["task__task_type__max_points"] or 1)
        mp = max(1, mp)

        if bool(row["is_correct"]):
            earned = float(mp)
        else:
            earned = float(row["tutor_primary_score"] or row["primary_score"] or row["score"] or 0)

        frac = max(0.0, min(1.0, earned / float(mp)))
        bucket = by_number.setdefault(number, {"wt": 0.0, "ws": 0.0, "total": 0.0, "correct": 0.0})
        bucket["wt"] += float(weight)
        bucket["ws"] += float(weight) * float(frac)
        bucket["total"] += float(mp)
        bucket["correct"] += float(earned)

    return by_number
```

- [ ] **Step 2: Wire helper into `build_task_type_rates()`**

Replace the current single-pass aggregation with:

```python
rows = list(
    submissions_scored.select_related("task", "task__task_type").values(
        "task_id",
        "task__task_type__number",
        "task__exam_points",
        "task__task_type__max_points",
        "created_at",
        "tutor_scored_at",
        "ai_last_verify_at",
        "is_correct",
        "tutor_primary_score",
        "primary_score",
        "score",
    )
)

current_agg = _rate_for_anchor(rows, anchor_day=today)
anchors = {days: _rate_for_anchor(rows, anchor_day=today - timezone.timedelta(days=days)) for days in RETROSPECTIVE_WINDOWS_DAYS}
```

Then build each tile with:

```python
task_type_rates.append(
    {
        "number": n,
        "name": task_type_name_map.get(n, ""),
        "rate": current_rate,
        "total": int(round(float(a["total"]))),
        "correct": int(round(float(a["correct"]))),
        "retrospective": [
            {"days_ago": days, "rate": retrospective_rate_for(days, n)}
            for days in sorted(RETROSPECTIVE_WINDOWS_DAYS, reverse=True)
        ],
    }
)
```

- [ ] **Step 3: Run tests to verify they pass**

Run:
```bash
python manage.py test core.tests.test_task_type_rate_retrospective -v 1
```
Expected: PASS

- [ ] **Step 4: Run nearby dashboard tests**

Run:
```bash
python manage.py test \
  core.tests.test_student_dashboard_task_type_rates \
  core.tests.test_tutor_solve_rate_decay \
  -v 1
```
Expected: existing expectations may fail until templates/views are updated; math-level tests should pass after subsequent tasks.

- [ ] **Step 5: Commit**

```bash
git add core/dashboard_analytics.py core/tests/test_task_type_rate_retrospective.py
git commit -m "feat: add retrospective task type solve-rate snapshots"
```

---

### Task 3: Перевести tutor dashboard на shared helper

**Files:**
- Modify: `/workspace/core/views.py`
- Test: `/workspace/core/tests/test_tutor_solve_rate_decay.py`

- [ ] **Step 1: Replace inline tutor logic**

In `tutor_dashboard`, import and use the shared helper:

```python
from core.dashboard_analytics import build_submission_summary, build_task_type_rates, build_weekly_solved_chart_data

task_type_rates, active_exam_format_label = build_task_type_rates(
    selected_student,
    subject_id=int(chart_subject_id) if chart_subject_id else None,
    exam_format=active_exam_format,
    today=today,
)
```

Delete the duplicated block that manually builds:

```python
submissions_base = ...
latest_rows = ...
half_life_days = 14.0
agg = {}
...
task_type_rates.append(...)
```

- [ ] **Step 2: Update/extend tutor tests**

Add or update assertions:

```python
tile = next(t for t in res.context["task_type_rates"] if int(t["number"]) == 2)
self.assertIn("retrospective", tile)
self.assertEqual([int(p["days_ago"]) for p in tile["retrospective"]], [50, 32, 16, 8, 4])
```

- [ ] **Step 3: Run tutor tests**

Run:
```bash
python manage.py test core.tests.test_tutor_solve_rate_decay -v 1
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/tests/test_tutor_solve_rate_decay.py
git commit -m "refactor: share task type solve-rate analytics with tutor dashboard"
```

---

### Task 4: Расширить student dashboard card

**Files:**
- Modify: `/workspace/core/templates/core/student_dashboard.html`
- Test: `/workspace/core/tests/test_student_dashboard_task_type_rates.py`

- [ ] **Step 1: Update card markup**

Replace the compact metric block inside each tile with:

```django
<div class="rounded-lg border border-gray-200 p-3 text-center bg-white task-type-tile"
     data-rate="{% if item.rate is None %}{% else %}{{ item.rate|floatformat:0 }}{% endif %}"
     title="{{ item.name|default:'' }}">
    <div class="text-xs font-black text-gray-800">{{ item.number }}</div>
    <div class="text-sm font-black text-gray-800 mt-1">
        {% if item.rate is None %}—{% else %}{{ item.rate|floatformat:0 }}%{% endif %}
    </div>
    <div class="mt-2 grid grid-cols-5 gap-1 text-[9px] text-gray-500">
        {% for point in item.retrospective %}
        <div>
            <div class="text-gray-400">{{ point.days_ago }}д</div>
            <div>{% if point.rate is None %}—{% else %}{{ point.rate|floatformat:0 }}{% endif %}</div>
        </div>
        {% endfor %}
    </div>
</div>
```

- [ ] **Step 2: Adjust grid density**

Update the surrounding grid classes to allow larger cards:

```django
<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
```

- [ ] **Step 3: Update student dashboard test**

Add render assertions:

```python
self.assertContains(res, "50д")
self.assertContains(res, "32д")
self.assertContains(res, "16д")
self.assertContains(res, "8д")
self.assertContains(res, "4д")
tile = next(r for r in res.context["task_type_rates"] if r["number"] == 1)
self.assertEqual(len(tile["retrospective"]), 5)
```

- [ ] **Step 4: Run student dashboard tests**

Run:
```bash
python manage.py test core.tests.test_student_dashboard_task_type_rates -v 1
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/templates/core/student_dashboard.html core/tests/test_student_dashboard_task_type_rates.py
git commit -m "feat: show task type solve-rate retrospective on student dashboard"
```

---

### Task 5: Расширить tutor dashboard card

**Files:**
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`
- Test: `/workspace/core/tests/test_tutor_solve_rate_decay.py`

- [ ] **Step 1: Mirror the student card changes**

Use the same tile structure and larger grid in tutor dashboard:

```django
<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
```

and:

```django
<div class="mt-2 grid grid-cols-5 gap-1 text-[9px] text-gray-500">
    {% for point in item.retrospective %}
    <div>
        <div class="text-gray-400">{{ point.days_ago }}д</div>
        <div>{% if point.rate is None %}—{% else %}{{ point.rate|floatformat:0 }}{% endif %}</div>
    </div>
    {% endfor %}
</div>
```

- [ ] **Step 2: Keep current color behavior**

Do not change the JS color logic:

```javascript
const r = Math.max(0, Math.min(100, parseInt(v, 10)));
const hue = Math.round((r / 100) * 120);
el.style.backgroundColor = `hsl(${hue} 80% 92%)`;
el.style.borderColor = `hsl(${hue} 60% 75%)`;
```

The background remains keyed to the current `rate`.

- [ ] **Step 3: Update tutor render assertions**

Add:

```python
self.assertContains(res, "50д")
self.assertContains(res, "4д")
tile = next(r for r in res.context["task_type_rates"] if int(r["number"]) == 2)
self.assertEqual(len(tile["retrospective"]), 5)
```

- [ ] **Step 4: Run tutor tests**

Run:
```bash
python manage.py test core.tests.test_tutor_solve_rate_decay -v 1
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/templates/core/tutor_dashboard.html core/tests/test_tutor_solve_rate_decay.py
git commit -m "feat: show task type solve-rate retrospective on tutor dashboard"
```

---

### Task 6: Full regression run and cleanup

**Files:**
- Modify: `/workspace/core/dashboard_analytics.py`
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/student_dashboard.html`
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`
- Test: `/workspace/core/tests/test_task_type_rate_retrospective.py`
- Test: `/workspace/core/tests/test_student_dashboard_task_type_rates.py`
- Test: `/workspace/core/tests/test_tutor_solve_rate_decay.py`

- [ ] **Step 1: Run focused regression suite**

Run:
```bash
python manage.py test \
  core.tests.test_task_type_rate_retrospective \
  core.tests.test_student_dashboard_task_type_rates \
  core.tests.test_tutor_solve_rate_decay \
  core.tests.test_student_dashboard_weekly_solved_and_summary \
  core.tests.test_tutor_dashboard_weekly_solved_chart \
  -v 1
```
Expected: PASS

- [ ] **Step 2: Check diagnostics on edited files**

Use diagnostics for:
- `/workspace/core/dashboard_analytics.py`
- `/workspace/core/views.py`
- `/workspace/core/templates/core/student_dashboard.html`
- `/workspace/core/templates/core/tutor_dashboard.html`

Expected: no new lint/template errors.

- [ ] **Step 3: Final commit**

```bash
git add core/dashboard_analytics.py core/views.py core/templates/core/student_dashboard.html core/templates/core/tutor_dashboard.html core/tests/test_task_type_rate_retrospective.py core/tests/test_student_dashboard_task_type_rates.py core/tests/test_tutor_solve_rate_decay.py
git commit -m "feat: add solve-rate retrospectives for task type cards"
```

---

## Self-review

- Spec coverage:
  - current rate preserved
  - retrospective snapshots added
  - stable nonlinear decay retained
  - tutor/student dashboards unified
- Placeholder scan:
  - no `TODO` / `TBD`
  - all tasks include files, commands, expected outcomes
- Consistency:
  - single source of truth in `build_task_type_rates()`
  - same retrospective windows in backend and templates
