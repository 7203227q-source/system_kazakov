# Weekly Chart Minutes Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В недельном графике “правильно/неправильно” показывать подписи `N мин` над днями, где ученик занимался, на student и tutor dashboard.

**Architecture:** `build_weekly_solved_chart_data()` расширяется: кроме `labels/correct/incorrect` добавляет `minutes` (сумма `TaskLog.time_spent` по дням за последние 7 дней по выбранному предмету, без аномалий). В шаблонах (Chart.js) добавляется легкий plugin, который после отрисовки баров пишет `N мин` над группой столбиков для каждого дня с `minutes[i] >= 1`.

**Tech Stack:** Django ORM, TaskLog, Chart.js, Django TestCase.

---

## Изменяемые файлы (map)

**Modify**
- `/workspace/core/dashboard_analytics.py` — добавить расчет `minutes` в `build_weekly_solved_chart_data`
- `/workspace/core/templates/core/student_dashboard.html` — добавить plugin отрисовки минут над днями
- `/workspace/core/templates/core/tutor_dashboard.html` — добавить plugin отрисовки минут над днями
- `/workspace/core/tests/test_student_dashboard_weekly_solved_and_summary.py` — добавить проверки `minutes`
- `/workspace/core/tests/test_tutor_dashboard_weekly_solved_chart.py` — добавить проверки `minutes`

---

### Task 1: Добавить failing tests на `minutes` в weekly_solved_chart_data

**Files:**
- Modify: `/workspace/core/tests/test_student_dashboard_weekly_solved_and_summary.py`
- Modify: `/workspace/core/tests/test_tutor_dashboard_weekly_solved_chart.py`

- [ ] **Step 1: Student — add failing assertion**

В `test_dashboard_provides_weekly_solved_chart_data_for_active_subject` добавить создание TaskLog для вчерашнего дня и проверку minutes.

```python
from core.models import TaskLog

        TaskLog.objects.create(
            student=self.student,
            task=self.task,
            submission=s2,
            time_spent=1800,
            is_anomaly=False,
        )

        self.assertEqual(len(data["minutes"]), 7)
        self.assertEqual(int(data["minutes"][idx]), 30)
```

- [ ] **Step 2: Tutor — add failing assertion**

В `test_weekly_chart_counts_unique_tasks_per_day_by_last_attempt` добавить TaskLog на день `d2` (или `d1`) и проверить `minutes`.

```python
from core.models import TaskLog

        TaskLog.objects.create(
            student=student,
            task=task_a,
            submission=s2,
            time_spent=600,
            is_anomaly=False,
        )

        self.assertEqual(len(data["minutes"]), 7)
        self.assertEqual(int(data["minutes"][idx_d2]), 10)
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
python manage.py test \
  core.tests.test_student_dashboard_weekly_solved_and_summary \
  core.tests.test_tutor_dashboard_weekly_solved_chart \
  -v 1
```
Expected: FAIL, key `minutes` missing.

- [ ] **Step 4: Commit**

```bash
git add core/tests/test_student_dashboard_weekly_solved_and_summary.py core/tests/test_tutor_dashboard_weekly_solved_chart.py
git commit -m "test: expect weekly chart minutes"
```

---

### Task 2: Реализовать `minutes` в `build_weekly_solved_chart_data`

**Files:**
- Modify: `/workspace/core/dashboard_analytics.py`
- Test: `/workspace/core/tests/test_student_dashboard_weekly_solved_and_summary.py`
- Test: `/workspace/core/tests/test_tutor_dashboard_weekly_solved_chart.py`

- [ ] **Step 1: Add TaskLog query and aggregation**

В `build_weekly_solved_chart_data`:

```python
from core.models import Submission, TaskType, TaskLog
```

Добавить выборку логов:

```python
log_qs = (
    TaskLog.objects.filter(
        student=student,
        task__topic__subject_id=int(subject_id),
        created_at__date__gte=start,
        created_at__date__lte=today,
        is_anomaly=False,
        time_spent__gt=0,
    )
    .values_list("created_at", "time_spent")
)

seconds_by_day: dict[object, int] = {}
for created_at, time_spent in log_qs:
    d = created_at.date()
    seconds_by_day[d] = int(seconds_by_day.get(d, 0)) + int(time_spent or 0)
```

Минуты для 7 дней:

```python
minutes: list[int] = []
for i in range(7):
    day = start + timedelta(days=i)
    minutes.append(int(round(float(seconds_by_day.get(day, 0)) / 60.0)))
```

И вернуть JSON:

```python
return json.dumps({"labels": labels, "correct": correct, "incorrect": incorrect, "minutes": minutes})
```

- [ ] **Step 2: Run tests to verify they pass**

Run:
```bash
python manage.py test \
  core.tests.test_student_dashboard_weekly_solved_and_summary \
  core.tests.test_tutor_dashboard_weekly_solved_chart \
  -v 1
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add core/dashboard_analytics.py
git commit -m "feat: add minutes to weekly solved chart data"
```

---

### Task 3: Отрисовать `N мин` над днями в student dashboard Chart.js

**Files:**
- Modify: `/workspace/core/templates/core/student_dashboard.html`

- [ ] **Step 1: Add plugin next to weekly chart init**

Перед `new Chart(...)` добавить:

```javascript
    const minutes = Array.isArray(weekly.minutes) ? weekly.minutes : null;
    const minutesPlugin = {
        id: 'minutesLabels',
        afterDatasetsDraw(chart) {
            if (!minutes || !minutes.length) return;
            const ctx = chart.ctx;
            const meta0 = chart.getDatasetMeta(0);
            const meta1 = chart.getDatasetMeta(1);
            if (!meta0 || !meta1) return;
            ctx.save();
            ctx.fillStyle = '#6b7280';
            ctx.font = 'bold 10px system-ui, -apple-system, Segoe UI, Roboto, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'bottom';
            for (let i = 0; i < minutes.length; i++) {
                const m = Number(minutes[i] || 0);
                if (!(m >= 1)) continue;
                const el0 = meta0.data[i];
                const el1 = meta1.data[i];
                if (!el0 || !el1) continue;
                const x = el0.x;
                const y = Math.min(el0.y, el1.y) - 6;
                ctx.fillText(`${m} мин`, x, y);
            }
            ctx.restore();
        }
    };
```

И передать в chart:

```javascript
plugins: [minutesPlugin],
```

- [ ] **Step 2: Manual sanity check**

Run:
```bash
python manage.py test core.tests.test_student_dashboard_weekly_solved_and_summary -v 1
```
Expected: PASS (без проверок JS).

- [ ] **Step 3: Commit**

```bash
git add core/templates/core/student_dashboard.html
git commit -m "feat: draw weekly minutes labels on student dashboard chart"
```

---

### Task 4: Отрисовать `N мин` над днями в tutor dashboard Chart.js

**Files:**
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`

- [ ] **Step 1: Add plugin to weekly chart init**

В блоке `studentWeeklySolvedChart` добавить аналогичный plugin и `plugins: [minutesPlugin]`.

- [ ] **Step 2: Run tutor weekly chart test**

Run:
```bash
python manage.py test core.tests.test_tutor_dashboard_weekly_solved_chart -v 1
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add core/templates/core/tutor_dashboard.html
git commit -m "feat: draw weekly minutes labels on tutor dashboard chart"
```

---

### Task 5: Focused regression suite

**Files:**
- Modify: `/workspace/core/dashboard_analytics.py`
- Modify: `/workspace/core/templates/core/student_dashboard.html`
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`
- Modify: `/workspace/core/tests/test_student_dashboard_weekly_solved_and_summary.py`
- Modify: `/workspace/core/tests/test_tutor_dashboard_weekly_solved_chart.py`

- [ ] **Step 1: Run focused regression suite**

Run:
```bash
python manage.py test \
  core.tests.test_student_dashboard_weekly_solved_and_summary \
  core.tests.test_tutor_dashboard_weekly_solved_chart \
  core.tests.test_tutor_dashboard_partial_points \
  -v 1
```
Expected: PASS

- [ ] **Step 2: Final commit**

```bash
git add core/dashboard_analytics.py core/templates/core/student_dashboard.html core/templates/core/tutor_dashboard.html core/tests/test_student_dashboard_weekly_solved_and_summary.py core/tests/test_tutor_dashboard_weekly_solved_chart.py
git commit -m "feat: show weekly activity minutes labels"
```

---

## Self-review

- Spec coverage:
  - `minutes` считаются из `TaskLog.time_spent` по дням и предмету
  - подписи рисуются только при `minutes[i] >= 1`
  - студент и репетитор используют одно поле `weekly_solved_chart_data`
- Placeholder scan:
  - нет `TODO/TBD`
- Consistency:
  - JSON-ключ `minutes` общий для обоих графиков
