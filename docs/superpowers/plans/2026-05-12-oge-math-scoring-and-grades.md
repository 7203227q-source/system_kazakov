# ОГЭ математика: шкала баллов/оценок (с геометрией) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить настраиваемую через Django admin шкалу ОГЭ математики (31 первичный балл, перевод в оценку 2–5 с условием геометрии), и показывать в UI «Прогноз/Текущий: X/31 (оценка Y)» вместо /100.

**Architecture:** Храним настройки шкалы в модели `ExamScoreScale` (OneToOne к `ExamFormat`). Геометрию помечаем флагом `TaskType.is_geometry`. Для отображения конвертируем `DailySnapshot.* (0–100)` в первичные баллы и оценку по правилам шкалы, включая условие `min_geometry`. Для ОГЭ математики задаём дефолты: геометрия = номера 15–19; пороги 0–7/8–14/15–21/22–31.

**Tech Stack:** Django models/migrations/admin, Django views/templates, unit tests (Django TestCase).

---

## Изменяемые файлы (map)

**Modify**
- `/workspace/core/models.py` — добавить `ExamScoreScale` и `TaskType.is_geometry`
- `/workspace/core/admin.py` — зарегистрировать `ExamScoreScale`, добавить отображение `is_geometry`
- `/workspace/core/views.py` — `student_dashboard`, `tutor_dashboard`: показывать баллы/оценку в UI-контексте
- `/workspace/core/templates/core/student_dashboard.html` — заменить `/100` на `/31 (оценка)`
- `/workspace/core/templates/core/tutor_dashboard.html` — заменить «Прогноз: …» на «Прогноз: …/31 (оценка …)» и добавить «Текущий: …»

**Create**
- `/workspace/core/migrations/00xx_exam_score_scale_and_geometry_flag.py` — миграция схемы
- `/workspace/core/migrations/00xy_seed_oge_math_scale_and_geometry.py` — data migration: дефолты для ОГЭ математики
- `/workspace/core/exam_scoring.py` — сервис конвертации (из 0–100 в первичку и оценку)
- `/workspace/core/tests/test_exam_scoring_oge_math.py` — тесты конвертации и UI

---

### Task 1: Тесты на конвертацию ОГЭ математики (порог + геометрия)

**Files:**
- Create: `/workspace/core/tests/test_exam_scoring_oge_math.py`

- [ ] **Step 1: Write failing tests**

```python
from django.test import TestCase

from core.exam_scoring import grade_from_primary, primary_from_percent, estimate_geometry_primary


class OgeMathExamScoringTests(TestCase):
    def test_primary_from_percent(self):
        self.assertEqual(primary_from_percent(0, 31), 0)
        self.assertEqual(primary_from_percent(100, 31), 31)
        self.assertEqual(primary_from_percent(50, 31), 16)  # round(15.5) -> 16

    def test_grade_thresholds_without_geometry(self):
        rules = [
            {"grade": 2, "min_total": 0, "max_total": 7, "min_geometry": None},
            {"grade": 3, "min_total": 8, "max_total": 14, "min_geometry": 2},
            {"grade": 4, "min_total": 15, "max_total": 21, "min_geometry": 2},
            {"grade": 5, "min_total": 22, "max_total": 31, "min_geometry": 2},
        ]
        # по сумме тянет на 3, но геометрии нет => 2
        self.assertEqual(grade_from_primary(10, geometry_primary=1, grade_rules=rules), 2)

        # по сумме 2 => 2 независимо от геометрии
        self.assertEqual(grade_from_primary(5, geometry_primary=0, grade_rules=rules), 2)

        # тянет на 4 и геометрия выполнена
        self.assertEqual(grade_from_primary(18, geometry_primary=2, grade_rules=rules), 4)

    def test_estimate_geometry_primary_by_share(self):
        # если геометрия ~ 1/3 экзамена, то при 18 баллах ожидаем ~6
        self.assertEqual(estimate_geometry_primary(total_primary=18, geometry_share=1/3), 6)
```

- [ ] **Step 2: Run to verify fails**

```bash
python manage.py test core.tests.test_exam_scoring_oge_math -v 1
```
Expected: FAIL (модуля `core.exam_scoring` ещё нет).

- [ ] **Step 3: Commit failing tests**

```bash
git add core/tests/test_exam_scoring_oge_math.py
git commit -m "test: OGE math exam scoring conversion"
```

---

### Task 2: Реализация сервиса конвертации (GREEN)

**Files:**
- Create: `/workspace/core/exam_scoring.py`
- Test: `/workspace/core/tests/test_exam_scoring_oge_math.py`

- [ ] **Step 1: Implement minimal service**

```python
# core/exam_scoring.py
from __future__ import annotations

from typing import Any


def primary_from_percent(pct: float | int | None, max_primary: int) -> int:
    try:
        v = float(pct or 0.0)
    except Exception:
        v = 0.0
    v = max(0.0, min(100.0, v))
    mp = int(max_primary or 0)
    if mp <= 0:
        return 0
    return int(round(v / 100.0 * mp))


def estimate_geometry_primary(*, total_primary: int, geometry_share: float) -> int:
    share = float(geometry_share or 0.0)
    share = max(0.0, min(1.0, share))
    return int(round(int(total_primary or 0) * share))


def grade_from_primary(total_primary: int, *, geometry_primary: int, grade_rules: list[dict[str, Any]]) -> int:
    total = int(total_primary or 0)
    geom = int(geometry_primary or 0)

    matched = None
    for r in grade_rules or []:
        try:
            lo = int(r.get("min_total"))
            hi = int(r.get("max_total"))
            if lo <= total <= hi:
                matched = r
                break
        except Exception:
            continue

    if not matched:
        # fallback: если правил нет, то не ломаемся
        return 0

    grade = int(matched.get("grade") or 0)
    min_geom = matched.get("min_geometry")
    if min_geom is not None:
        try:
            if geom < int(min_geom):
                return 2
        except Exception:
            return 2
    return grade
```

- [ ] **Step 2: Run tests**

```bash
python manage.py test core.tests.test_exam_scoring_oge_math -v 1
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add core/exam_scoring.py
git commit -m "feat: exam scoring conversion helpers"
```

---

### Task 3: Добавить модели и миграции (ExamScoreScale, TaskType.is_geometry)

**Files:**
- Modify: `/workspace/core/models.py`
- Create: `/workspace/core/migrations/00xx_exam_score_scale_and_geometry_flag.py`

- [ ] **Step 1: Add models/fields (no behavior changes yet)**

В `core/models.py`:
1) В `TaskType` добавить:

```python
is_geometry = models.BooleanField(default=False, verbose_name="Геометрия (для ОГЭ)")
```

2) Добавить модель:

```python
class ExamScoreScale(models.Model):
    exam_format = models.OneToOneField(ExamFormat, on_delete=models.CASCADE, related_name="score_scale")
    max_primary_score = models.PositiveIntegerField(default=100)
    grade_rules = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"Scale for {self.exam_format}"
```

- [ ] **Step 2: Make migrations**

```bash
python manage.py makemigrations core
```

- [ ] **Step 3: Run minimal tests**

```bash
python manage.py test core.tests.test_exam_scoring_oge_math -v 1
```

- [ ] **Step 4: Commit**

```bash
git add core/models.py core/migrations
git commit -m "feat: add exam score scale and geometry flag"
```

---

### Task 4: Data migration — дефолты ОГЭ математики (шкала + геометрия 15–19)

**Files:**
- Create: `/workspace/core/migrations/00xy_seed_oge_math_scale_and_geometry.py`

- [ ] **Step 1: Write migration**

Миграция должна:
1) найти `ExamFormat` где:
   - `subject.name == "Математика"`
   - `name` содержит `"ОГЭ"` (case-insensitive)
2) для каждого такого `ExamFormat`:
   - создать `ExamScoreScale`, если нет:
     - `max_primary_score = 31`
     - `grade_rules` как в PDF 2025:
       - 2: 0–7
       - 3: 8–14, min_geometry=2
       - 4: 15–21, min_geometry=2
       - 5: 22–31, min_geometry=2
   - пометить `TaskType.is_geometry=True` для `number in [15,16,17,18,19]` в рамках этого `ExamFormat`

- [ ] **Step 2: Run migrations + tests**

```bash
python manage.py test core.tests.test_exam_scoring_oge_math -v 1
```

- [ ] **Step 3: Commit**

```bash
git add core/migrations
git commit -m "feat: seed OGE math scale and geometry task numbers"
```

---

### Task 5: Django admin — управление шкалой и геометрией

**Files:**
- Modify: `/workspace/core/admin.py`

- [ ] **Step 1: Register ExamScoreScale and show TaskType.is_geometry**

```python
from .models import ExamScoreScale

@admin.register(ExamScoreScale)
class ExamScoreScaleAdmin(admin.ModelAdmin):
    list_display = ("exam_format", "max_primary_score")
    search_fields = ("exam_format__name", "exam_format__subject__name")

@admin.register(TaskType)
class TaskTypeAdmin(admin.ModelAdmin):
    list_display = ("exam_format", "number", "name", "max_points", "is_geometry")
    list_filter = ("exam_format", "exam_format__subject", "is_geometry")
    search_fields = ("name",)
```

Примечание: нужно убрать `admin.site.register(TaskType)` если он уже зарегистрирован.

- [ ] **Step 2: Run system checks**

```bash
python manage.py check
```

- [ ] **Step 3: Commit**

```bash
git add core/admin.py
git commit -m "feat: admin for exam scales and geometry flag"
```

---

### Task 6: Вывод в UI (student_dashboard + tutor_dashboard)

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/student_dashboard.html`
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`
- Test: `/workspace/core/tests/test_exam_scoring_oge_math.py`

- [ ] **Step 1: Add helper in views to compute display fields**

В `views.py` при сборе `latest_snapshot` для `(student, subject)`:
1) определить `exam_format` из `StudentSubjectProfile.exam_format` (как уже делалось для других мест);
2) взять `scale = getattr(exam_format, "score_scale", None)`;
3) если `scale` есть:
   - `max_primary = scale.max_primary_score`
   - `cur_primary = primary_from_percent(latest_snapshot.current_mastery, max_primary)`
   - `pred_primary = primary_from_percent(latest_snapshot.predicted_exam_score, max_primary)`
   - `geometry_share = sum(exam_points for TaskType.is_geometry)/sum(exam_points for all TaskType in exam_format)` (fallback 0)
   - `cur_geom = estimate_geometry_primary(cur_primary, geometry_share)`
   - `pred_geom = estimate_geometry_primary(pred_primary, geometry_share)`
   - `cur_grade = grade_from_primary(cur_primary, geometry_primary=cur_geom, grade_rules=scale.grade_rules)`
   - `pred_grade = grade_from_primary(pred_primary, geometry_primary=pred_geom, grade_rules=scale.grade_rules)`
4) положить в контекст/атрибуты профиля (например `profile.display_exam = {...}`).

- [ ] **Step 2: Update templates**

`student_dashboard.html`:
- заменить “/100” на “/{{ max_primary }} (оценка {{ pred_grade }})”
- аналогично для текущего мастерства.

`tutor_dashboard.html`:
- в блоке профилей заменить:
  - `Прогноз: {{ profile.latest_snapshot.predicted_exam_score }}`
  на:
  - `Прогноз: {{ pred_primary }}/{{ max_primary }} (оценка {{ pred_grade }})`
  и добавить строку “Текущий: …”.

- [ ] **Step 3: Add view/template test**

Добавить в `test_exam_scoring_oge_math.py` тест рендера tutor_dashboard (минимум):

```python
from django.urls import reverse
from core.models import DailySnapshot

def test_tutor_dashboard_shows_oge_points_and_grade(self):
    # создать snapshot mastery=50 pred=80 => 16/31 и 25/31
    # и ожидать строку "Прогноз: 25/31" и "оценка"
    ...
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test core.tests.test_exam_scoring_oge_math -v 1
```

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/templates/core/student_dashboard.html core/templates/core/tutor_dashboard.html core/tests/test_exam_scoring_oge_math.py
git commit -m "feat: show OGE math points and grade in dashboards"
```

---

### Task 7: Прогон всего сьюта и пуш

- [ ] **Step 1: Run full tests**

```bash
python manage.py test core.tests -v 1
```

- [ ] **Step 2: Push**

```bash
git push origin HEAD:main
```

---

## Self-review (plan vs spec)
- `ExamScoreScale` + `TaskType.is_geometry` + дефолты 15–19: Tasks 3–5
- Перевод в баллы+оценку с условием геометрии: Tasks 1–2 + Task 6
- UI: Task 6

