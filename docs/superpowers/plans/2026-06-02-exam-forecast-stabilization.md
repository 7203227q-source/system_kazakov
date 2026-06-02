# Exam Forecast Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** сделать прогноз `DailySnapshot.predicted_exam_score` менее волатильным и менее склонным “упираться” в 100 за счёт стабилизации входных сигналов, тренда и `learning_velocity`, сохранив шкалу 0–100 и показ “оба значения” (проценты + первичные баллы) в UI.

**Architecture:** расчёт остаётся в [core/analytics.py](file:///workspace/core/analytics.py) внутри `update_student_analytics`, но добавляются: shrinkage для `recent_perf`, ограниченный горизонт тренда, сглаживание прогноза по предыдущему снэпшоту с лимитом дневного шага, а также более мягкая калибровка `learning_velocity`.

**Tech Stack:** Django, Django ORM, Django TestCase, HTML templates.

---

### Task 1: Tests for Stabilization Math + Updated Velocity Calibration

**Files:**
- Create: [test_exam_forecast_stabilization_helpers.py](file:///workspace/core/tests/test_exam_forecast_stabilization_helpers.py)
- Modify: [test_learning_velocity_calibration.py](file:///workspace/core/tests/test_learning_velocity_calibration.py)
- Modify: [test_exam_date_forecast.py](file:///workspace/core/tests/test_exam_date_forecast.py)

- [ ] **Step 1: Add helper-function tests (failing first)**

Create [test_exam_forecast_stabilization_helpers.py](file:///workspace/core/tests/test_exam_forecast_stabilization_helpers.py):

```python
from django.test import TestCase


class ExamForecastStabilizationHelpersTests(TestCase):
    def test_shrink_recent_perf_small_weight_stays_near_mastery(self):
        from core.analytics import _shrink_recent_perf

        current_mastery = 50.0
        recent_perf = 100.0
        recent_weight = 1.0

        recent_adj = _shrink_recent_perf(
            current_mastery=current_mastery,
            recent_perf=recent_perf,
            recent_weight=recent_weight,
        )
        self.assertGreaterEqual(recent_adj, 50.0)
        self.assertLess(recent_adj, 60.0)

    def test_shrink_recent_perf_large_weight_moves_towards_recent(self):
        from core.analytics import _shrink_recent_perf

        current_mastery = 50.0
        recent_perf = 100.0
        recent_weight = 40.0

        recent_adj = _shrink_recent_perf(
            current_mastery=current_mastery,
            recent_perf=recent_perf,
            recent_weight=recent_weight,
        )
        self.assertGreater(recent_adj, 80.0)
        self.assertLessEqual(recent_adj, 100.0)

    def test_smooth_prediction_limits_daily_step(self):
        from core.analytics import _smooth_prediction

        prev_pred = 50.0
        raw_pred = 90.0

        pred = _smooth_prediction(prev_pred=prev_pred, raw_pred=raw_pred)
        self.assertLessEqual(pred, 56.0)
        self.assertGreaterEqual(pred, 50.0)
```

- [ ] **Step 2: Run the new tests to confirm they fail**

Run:

```bash
python manage.py test core.tests.test_exam_forecast_stabilization_helpers -v 2
```

Expected: FAIL (`ImportError` / missing helpers) until Task 2 is implemented.

- [ ] **Step 3: Update learning-velocity calibration expectations (failing first)**

Edit [test_learning_velocity_calibration.py](file:///workspace/core/tests/test_learning_velocity_calibration.py) to match the new constants:

- In `test_learning_velocity_calibrates_on_finish_assignment_with_warmup` replace the expected value with:

```python
# err=+50, k=0.15 => 0.075, clamp => 0.06, warmup(0) => *0.3 => 0.018
self.assertAlmostEqual(float(self.profile.learning_velocity), 1.018, places=3)
```

- In `test_learning_velocity_penalizes_late_assignments` replace the expected value with:

```python
# 0.018 * deadline_weight(0.2) => 0.0036
self.assertAlmostEqual(float(self.profile.learning_velocity), 1.0036, places=4)
```

- [ ] **Step 4: Run the two calibration tests to confirm they fail**

Run:

```bash
python manage.py test core.tests.test_learning_velocity_calibration -v 2
```

Expected: FAIL until Task 2 updates calibration logic.

- [ ] **Step 5: Sanity-check exam_date forecast tests against “still grows” behavior**

Keep assertions in [test_exam_date_forecast.py](file:///workspace/core/tests/test_exam_date_forecast.py) as-is initially; if the new smoothing makes them too strict, adjust only minimally:

```python
self.assertGreater(float(snap.predicted_exam_score), 50.0)
```

- [ ] **Step 6: Commit**

```bash
git add core/tests/test_exam_forecast_stabilization_helpers.py core/tests/test_learning_velocity_calibration.py
git commit -m "test: add forecast stabilization coverage"
```

### Task 2: Implement Stabilized Forecast in core/analytics.py

**Files:**
- Modify: [analytics.py](file:///workspace/core/analytics.py)

- [ ] **Step 1: Add constants next to ALPHA**

In [analytics.py](file:///workspace/core/analytics.py), below `ALPHA`, add:

```python
RECENT_SHRINK_K = 10.0
TREND_HORIZON_DAYS = 30
TREND_MAX_DELTA = 20.0
PRED_SMOOTH_BETA = 0.35
PRED_MAX_STEP_UP = 6.0
PRED_MAX_STEP_DOWN = 8.0
```

- [ ] **Step 2: Add small pure helpers for tests**

Add these helpers in [analytics.py](file:///workspace/core/analytics.py) near the constants:

```python
def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _shrink_recent_perf(*, current_mastery: float, recent_perf: float, recent_weight: float) -> float:
    rm = float(current_mastery or 0.0)
    rp = float(recent_perf or 0.0)
    rw = max(0.0, float(recent_weight or 0.0))
    w = rw / (rw + float(RECENT_SHRINK_K))
    return rm + w * (rp - rm)


def _smooth_prediction(*, prev_pred: float, raw_pred: float) -> float:
    prev = float(prev_pred or 0.0)
    raw = float(raw_pred or 0.0)
    pred = (float(PRED_SMOOTH_BETA) * raw) + ((1.0 - float(PRED_SMOOTH_BETA)) * prev)
    return _clamp(pred, prev - float(PRED_MAX_STEP_DOWN), prev + float(PRED_MAX_STEP_UP))
```

- [ ] **Step 3: Wire shrinkage into recent_perf block**

In `update_student_analytics`:
- keep сбор `perf_logs`
- дополнительно считать `recent_weight = sum(w)`
- заменить прямое использование `recent_perf` на:

```python
recent_adj = _shrink_recent_perf(
    current_mastery=float(current_mastery),
    recent_perf=float(recent_perf),
    recent_weight=float(recent_weight),
)
blended_mastery = 0.7 * float(current_mastery) + 0.3 * float(recent_adj)
perf_delta = float(recent_perf) - float(current_mastery)
```

- [ ] **Step 4: Limit trend horizon and delta**

In the `exam_date` section:
- compute `h = min(days_left, TREND_HORIZON_DAYS)`
- compute `trend_delta = _clamp(slope * float(h), -TREND_MAX_DELTA, TREND_MAX_DELTA)`
- use `projected_mastery = float(blended_mastery) + float(trend_delta)`

- [ ] **Step 5: Apply smoothing vs previous snapshot**

Before writing `snapshot.predicted_exam_score`:
- fetch `prev_pred`:

```python
prev = (
    DailySnapshot.objects.filter(student=student, subject=subject, date__lt=today)
    .order_by("-date")
    .values_list("predicted_exam_score", flat=True)
    .first()
)
```

- then:

```python
raw_pred = float(predicted_score)
if prev is not None:
    predicted_score = _smooth_prediction(prev_pred=float(prev), raw_pred=raw_pred)
else:
    predicted_score = raw_pred
```

- final clamp to [0..100] stays.

- [ ] **Step 6: Stabilize learning_velocity calibration**

In `calibrate_learning_velocity_for_assignment`:
- change `k = 0.25` → `k = 0.15`
- change `delta clamp` from `[-0.10..0.10]` → `[-0.06..0.06]`
- change `new_lv clamp` from `[0.5..1.5]` → `[0.7..1.3]`

- [ ] **Step 7: Run focused tests**

Run:

```bash
python manage.py test \
  core.tests.test_exam_forecast_stabilization_helpers \
  core.tests.test_learning_velocity_calibration \
  core.tests.test_exam_date_forecast \
  -v 2
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/analytics.py
git commit -m "feat: stabilize exam forecast"
```

### Task 3: Show Both Values in UI (Student/Tutor/Parent)

**Files:**
- Modify: [student_dashboard.html](file:///workspace/core/templates/core/student_dashboard.html)
- Modify: [tutor_dashboard.html](file:///workspace/core/templates/core/tutor_dashboard.html)
- Modify: [views.py](file:///workspace/core/views.py) (`parent_dashboard`)
- Modify: [parent_dashboard.html](file:///workspace/core/templates/core/parent_dashboard.html)

- [ ] **Step 1: Student dashboard shows percent + primary**

In [student_dashboard.html](file:///workspace/core/templates/core/student_dashboard.html) in “Прогноз ИИ на экзамен” block, keep the big primary value, and add a second line for percent:

```django
{% if exam_display %}
  <h3 class="text-3xl font-bold text-primary">
    {{ exam_display.pred_primary }}/{{ exam_display.max_primary }}
    <span class="text-base text-gray-500">(оценка {{ exam_display.pred_grade }})</span>
  </h3>
  <div class="text-sm text-gray-500 mt-1">
    ≈ {{ latest_snapshot.predicted_exam_score|default:"-" }}/100
  </div>
{% else %}
  ...
{% endif %}
```

- [ ] **Step 2: Tutor dashboard shows percent + primary**

In [tutor_dashboard.html](file:///workspace/core/templates/core/tutor_dashboard.html) in the “Прогноз” line for `profile.exam_display`, add the percent next to it:

```django
{% if profile.exam_display %}
  Прогноз: {{ profile.exam_display.pred_primary }}/{{ profile.exam_display.max_primary }}
  ({{ profile.latest_snapshot.predicted_exam_score|default:"-" }}/100, оценка {{ profile.exam_display.pred_grade }})
{% else %}
  ...
{% endif %}
```

- [ ] **Step 3: Add exam_display computation to parent_dashboard view**

In [views.py](file:///workspace/core/views.py#L5200-L5259) for each `profile` inside the `children` loop:
- compute `profile.exam_display` similarly to tutor_dashboard:
  - find `exam_format` (`profile.exam_format` if есть, иначе активный по subject)
  - use `core.exam_scoring.primary_from_percent`
  - use `score_scale.max_primary_score`
  - fill dict keys: `max_primary`, `pred_primary`

Keep it defensive: if нет `latest_snapshot` или `scale`, set `profile.exam_display = None`.

- [ ] **Step 4: Parent dashboard template shows both values**

In [parent_dashboard.html](file:///workspace/core/templates/core/parent_dashboard.html), replace the single percent badge with:

```django
{% if profile.exam_display %}
  <span class="text-xs bg-indigo-100 text-indigo-800 px-2 py-1 rounded font-bold" title="Текущий прогноз ИИ">
    Прогноз: {{ profile.exam_display.pred_primary }}/{{ profile.exam_display.max_primary }}
    ({{ profile.latest_snapshot.predicted_exam_score|default:"-" }}/100)
  </span>
{% else %}
  <span class="text-xs bg-indigo-100 text-indigo-800 px-2 py-1 rounded font-bold" title="Текущий прогноз ИИ">
    Прогноз: {{ profile.latest_snapshot.predicted_exam_score|default:"-" }}
  </span>
{% endif %}
```

- [ ] **Step 5: Run UI-smoke tests (optional)**

If there are existing tests that assert dashboard strings, run a small subset:

```bash
python manage.py test core.tests.test_student_dashboard_subject_id_parsing -v 2
```

- [ ] **Step 6: Commit**

```bash
git add core/templates/core/student_dashboard.html core/templates/core/tutor_dashboard.html core/templates/core/parent_dashboard.html core/views.py
git commit -m "feat: show exam forecast in percent and primary"
```

### Task 4: Verification Pass

**Files:**
- (no new files)

- [ ] **Step 1: Run the focused suite**

```bash
python manage.py test \
  core.tests.test_exam_forecast_stabilization_helpers \
  core.tests.test_exam_date_forecast \
  core.tests.test_learning_velocity_calibration \
  -v 2
```

Expected: PASS.

- [ ] **Step 2: Run full test suite (optional in CI)**

```bash
python manage.py test -v 1
```

- [ ] **Step 3: Manual UI sanity**
- Student dashboard: прогноз показывает “X/Y” и “≈ Z/100”, прогресс-бар совпадает с `Z/100`
- Tutor dashboard: в карточках предметов прогноз показывает и первичные, и /100
- Parent dashboard: аналогично

---

## Plan Self-Review

- Spec coverage:
  - shrinkage `recent_perf` → Task 2 Step 3
  - тренд ограничен горизонтом/дельтой → Task 2 Step 4
  - сглаживание по предыдущему дню + лимит шага → Task 2 Step 5 + tests in Task 1
  - стабилизация `learning_velocity` → Task 2 Step 6 + updates in Task 1
  - “оба значения” в UI → Task 3
- Placeholder scan: no TODO/TBD sections, every step contains concrete code/commands.

