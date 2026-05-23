# Tutor Dashboard Partial Points Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В панели репетитора на дашборде учитывать частично набранные первичные баллы при расчёте «Решаемости по номерам», weekly-графика «правильно/неправильно» и показателя «Точность», не меняя UI.

**Architecture:** В `tutor_dashboard` заменить бинарную метрику `is_correct` на долю набранных первичных баллов `earned/max_points` (где `earned` берётся из `tutor_primary_score`/`primary_score`, а для `is_correct=True` считается полным баллом). Для плиток сохраняем затухание по давности (half-life), но агрегируем по долям. Для weekly-графика считаем суммы набранных/потерянных баллов за день по последней попытке в день на задачу. Для «Точности» считаем общий процент набранных баллов от максимума по попыткам.

**Tech Stack:** Django, Django ORM (Subquery/OuterRef), Django templates, Python, unit tests (Django TestCase).

---

## Изменяемые файлы (map)

**Modify**
- [views.py](file:///workspace/core/views.py#L2568-L2736) — `tutor_dashboard`: weekly-график, `task_type_rates`, `student_correct_rate`

**Create**
- ` /workspace/core/tests/test_tutor_dashboard_partial_points.py` — тесты на доли баллов (1 из 3 = 33%)

---

## Правило расчёта доли баллов (единое)

Внутри `tutor_dashboard` (или рядом с ним) завести небольшую функцию, которая из данных последнего сабмита + максимального балла задачи возвращает:
- `max_points` (int, >= 1)
- `earned` (float, >= 0)
- `fraction = earned/max_points` (float, 0..1)

Правила:
- `max_points = task.exam_points`, если задан и > 0, иначе `task.task_type.max_points`, иначе 1
- если `is_correct is True`: `earned = max_points`
- иначе:
  - если `tutor_primary_score is not None`: `earned = tutor_primary_score`
  - elif `primary_score is not None`: `earned = primary_score`
  - else `earned = 0`
- clamp: `earned` в диапазон `[0, max_points]` (чтобы не улетать за максимум)

---

### Task 1: Написать падающий тест на частичные баллы (tiles + weekly + точность)

**Files:**
- Create: `/workspace/core/tests/test_tutor_dashboard_partial_points.py`

- [ ] **Step 1: Write failing test**

```python
import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    DailySnapshot,
    ExamFormat,
    StudentSubjectProfile,
    Subject,
    Submission,
    Task,
    TaskType,
    Topic,
    User,
)


class TutorDashboardPartialPointsTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        self.subject = Subject.objects.create(name="Физика")
        self.ef = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        self.tt = TaskType.objects.create(exam_format=self.ef, number=1, name="N1", max_points=3)

        topic = Topic.objects.create(subject=self.subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=self.tt, correct_answer="x", difficulty=50, exam_points=3)

        StudentSubjectProfile.objects.create(student=self.student, subject=self.subject, exam_format=self.ef)
        DailySnapshot.objects.create(student=self.student, subject=self.subject, date=timezone.localdate())

    def test_partial_points_affect_tiles_weekly_and_accuracy(self):
        now = timezone.now()

        sub = Submission.objects.create(
            student=self.student,
            task=self.task,
            is_correct=False,
            tutor_primary_score=1,
        )
        Submission.objects.filter(id=sub.id).update(created_at=now)

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"), {"student_id": self.student.id, "subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)

        tiles = list(res.context["task_type_rates"])
        tile = next(t for t in tiles if int(t["number"]) == 1)

        self.assertEqual(int(tile["total"]), 3)
        self.assertEqual(int(tile["correct"]), 1)
        self.assertEqual(int(round(float(tile["rate"] or 0.0))), 33)

        self.assertEqual(int(round(float(res.context["student_correct_rate"] or 0.0))), 33)

        weekly = json.loads(res.context["weekly_solved_chart_data"])
        self.assertEqual(int(weekly["correct"][-1]), 1)
        self.assertEqual(int(weekly["incorrect"][-1]), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python manage.py test core.tests.test_tutor_dashboard_partial_points -v 2
```

Expected: FAIL (пока везде используется бинарный `is_correct` и считаются количества задач, а не доли/баллы).

- [ ] **Step 3: Commit failing test**

```bash
git add core/tests/test_tutor_dashboard_partial_points.py
git commit -m "test: tutor dashboard partial points in tiles and charts"
```

---

### Task 2: Реализовать общий хелпер расчёта earned/max/fraction в tutor_dashboard

**Files:**
- Modify: `/workspace/core/views.py` (внутри `tutor_dashboard`, рядом с блоками расчёта графиков)
- Test: `/workspace/core/tests/test_tutor_dashboard_partial_points.py`

- [ ] **Step 1: Add helper inside tutor_dashboard**

Внутри `tutor_dashboard` (перед блоками weekly/task_type_rates/student_correct_rate) добавить:

```python
def _earned_max_fraction(*, is_correct, tutor_primary_score, primary_score, task_exam_points, task_type_max_points):
    mp = int(task_exam_points or 0) if int(task_exam_points or 0) > 0 else int(task_type_max_points or 0)
    if mp <= 0:
        mp = 1

    if is_correct is True:
        earned = float(mp)
    else:
        if tutor_primary_score is not None:
            earned = float(tutor_primary_score)
        elif primary_score is not None:
            earned = float(primary_score)
        else:
            earned = 0.0

    if earned < 0.0:
        earned = 0.0
    if earned > float(mp):
        earned = float(mp)

    frac = (earned / float(mp)) if mp > 0 else 0.0
    if frac < 0.0:
        frac = 0.0
    if frac > 1.0:
        frac = 1.0
    return earned, mp, frac
```

- [ ] **Step 2: Run test to verify it still fails**

Run:
```bash
python manage.py test core.tests.test_tutor_dashboard_partial_points -v 2
```

Expected: FAIL (пока логика не применена к агрегатам).

- [ ] **Step 3: Commit**

```bash
git add core/views.py
git commit -m "refactor: add earned/max helper for tutor dashboard"
```

---

### Task 3: Пересчитать weekly-график в баллах (earned vs lost)

**Files:**
- Modify: `/workspace/core/views.py` (блок `weekly_solved_chart_data`, сейчас [views.py:L2568-L2606](file:///workspace/core/views.py#L2568-L2606))
- Test: `/workspace/core/tests/test_tutor_dashboard_partial_points.py`

- [ ] **Step 1: Update queryset to include score fields and max points**

Заменить выборку `qs = Submission.objects.filter(... is_correct__isnull=False ...)` на:

```python
qs = (
    Submission.objects.filter(
        student=selected_student,
        created_at__date__gte=start_week,
        created_at__date__lte=today,
    )
    .filter(task__topic__subject_id=chart_subject_id)
    .order_by("created_at")
    .values_list(
        "created_at",
        "task_id",
        "is_correct",
        "tutor_primary_score",
        "primary_score",
        "task__exam_points",
        "task__task_type__max_points",
    )
)
```

- [ ] **Step 2: Store last earned/max per (day, task) and aggregate**

Заменить `last_by_day_task[(date, task_id)] = bool(is_correct)` на:

```python
last_by_day_task: dict[tuple, tuple[float, int]] = {}
for created_at, task_id, is_correct, tutor_primary_score, primary_score, task_exam_points, task_type_max_points in qs:
    earned, mp, _ = _earned_max_fraction(
        is_correct=is_correct,
        tutor_primary_score=tutor_primary_score,
        primary_score=primary_score,
        task_exam_points=task_exam_points,
        task_type_max_points=task_type_max_points,
    )
    last_by_day_task[(created_at.date(), int(task_id))] = (float(earned), int(mp))
```

И заменить агрегацию `by_day` на:

```python
by_day: dict = {}
for (d, _tid), v in last_by_day_task.items():
    earned, mp = v
    cell = by_day.setdefault(d, {"correct": 0.0, "incorrect": 0.0})
    cell["correct"] = float(cell["correct"]) + float(earned)
    cell["incorrect"] = float(cell["incorrect"]) + float(mp - earned)

weekly_correct = [int(round(float(by_day.get(d, {}).get("correct", 0.0)))) for d in day_list]
weekly_incorrect = [int(round(float(by_day.get(d, {}).get("incorrect", 0.0)))) for d in day_list]
```

- [ ] **Step 3: Run test to verify weekly part passes**

Run:
```bash
python manage.py test core.tests.test_tutor_dashboard_partial_points.TutorDashboardPartialPointsTests::test_partial_points_affect_tiles_weekly_and_accuracy -v 2
```

Expected: Still FAIL on tiles/accuracy, но weekly assertions должны стать TRUE (если временно закомментировать другие asserts).

- [ ] **Step 4: Commit**

```bash
git add core/views.py
git commit -m "feat: weekly solved chart uses earned/lost points"
```

---

### Task 4: Пересчитать «Решаемость по номерам» как среднюю долю (с затуханием) + показывать earned/max внизу

**Files:**
- Modify: `/workspace/core/views.py` (блок `task_type_rates`, сейчас [views.py:L2674-L2736](file:///workspace/core/views.py#L2674-L2736))
- Test: `/workspace/core/tests/test_tutor_dashboard_partial_points.py`

- [ ] **Step 1: Extend latest_rows with score + max-point fields**

Дополнить аннотации `latest_rows`:

```python
last_tutor_primary = Subquery(last_sub.values("tutor_primary_score")[:1])
last_primary = Subquery(last_sub.values("primary_score")[:1])
```

И добавить в `.annotate(...)`:

```python
last_tutor_primary_score=last_tutor_primary,
last_primary_score=last_primary,
```

Также расширить `values(...)` до:

```python
latest_rows = (
    submissions_base.values(
        "task_id",
        "task__task_type__number",
        "task__exam_points",
        "task__task_type__max_points",
    )
    .distinct()
    .annotate(
        last_created_at=Subquery(last_sub.values("created_at")[:1]),
        last_is_correct=Subquery(last_sub.values("is_correct")[:1]),
        last_tutor_primary_score=last_tutor_primary,
        last_primary_score=last_primary,
    )
)
```

- [ ] **Step 2: Aggregate using fraction and also sum earned/max for display**

Заменить вычисление `is_corr = bool(r.get("last_is_correct"))` и `wc += weight * (1 if is_corr else 0)` на:

```python
earned, mp, frac = _earned_max_fraction(
    is_correct=r.get("last_is_correct"),
    tutor_primary_score=r.get("last_tutor_primary_score"),
    primary_score=r.get("last_primary_score"),
    task_exam_points=r.get("task__exam_points"),
    task_type_max_points=r.get("task__task_type__max_points"),
)
a = agg.setdefault(n, {"wt": 0.0, "ws": 0.0, "total": 0.0, "correct": 0.0})
a["wt"] = float(a["wt"]) + float(weight)
a["ws"] = float(a["ws"]) + float(weight) * float(frac)
a["total"] = float(a["total"]) + float(mp)
a["correct"] = float(a["correct"]) + float(earned)
```

И при формировании `task_type_rates`:

```python
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
```

- [ ] **Step 3: Run test to verify tiles pass**

Run:
```bash
python manage.py test core.tests.test_tutor_dashboard_partial_points.TutorDashboardPartialPointsTests::test_partial_points_affect_tiles_weekly_and_accuracy -v 2
```

Expected: Still FAIL on «Точность», но assertions по tile.rate и tile.correct/tile.total должны стать TRUE (если временно закомментировать accuracy assert).

- [ ] **Step 4: Commit**

```bash
git add core/views.py
git commit -m "feat: task type tiles use partial points fraction with decay"
```

---

### Task 5: Пересчитать «Точность» как Σearned / Σmax по попыткам

**Files:**
- Modify: `/workspace/core/views.py` (блок `student_correct_rate`, сейчас [views.py:L2713-L2719](file:///workspace/core/views.py#L2713-L2719))
- Test: `/workspace/core/tests/test_tutor_dashboard_partial_points.py`

- [ ] **Step 1: Replace count-based aggregate with points-based aggregate**

Заменить:

```python
totals = submissions_subject.aggregate(
    total=models.Count('id'),
    correct=models.Count('id', filter=Q(is_correct=True)),
)
student_total_submissions = int(totals.get('total') or 0)
correct_total = int(totals.get('correct') or 0)
student_correct_rate = (correct_total / student_total_submissions * 100.0) if student_total_submissions else None
```

на:

```python
from django.db.models import Case, When, Value, FloatField, IntegerField
from django.db.models.functions import Coalesce

max_points_expr = Case(
    When(task__exam_points__gt=0, then=Coalesce("task__exam_points", Value(1))),
    default=Coalesce("task__task_type__max_points", Value(1)),
    output_field=IntegerField(),
)

earned_expr = Case(
    When(is_correct=True, then=Coalesce("task__exam_points", Value(1))),
    default=Coalesce("tutor_primary_score", "primary_score", Value(0)),
    output_field=FloatField(),
)

totals = submissions_subject.aggregate(
    max_total=models.Sum(max_points_expr),
    earned_total=models.Sum(earned_expr),
    attempts=models.Count("id"),
)
student_total_submissions = int(totals.get("attempts") or 0)
max_total = float(totals.get("max_total") or 0.0)
earned_total = float(totals.get("earned_total") or 0.0)
student_correct_rate = (earned_total / max_total * 100.0) if max_total > 0 else None
```

- [ ] **Step 2: Run full test**

Run:
```bash
python manage.py test core.tests.test_tutor_dashboard_partial_points -v 2
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add core/views.py
git commit -m "feat: tutor dashboard accuracy uses earned/max points"
```

---

## Manual checks (после unit tests)

- Открыть дашборд репетитора и выбрать ученика/предмет (физика ОГЭ/ЕГЭ и математика часть 2).
- Убедиться, что:
  - в плитках «Решаемость по номерам» процент стал учитывать частичные баллы (1/3 → 33%)
  - подпись `x/y` под плиткой отражает сумму набранных/максимальных первичных баллов (а не число задач)
  - weekly-график изменился по смыслу на баллы (но отображение осталось тем же)
  - «Точность» соответствует доле набранных первичных баллов

