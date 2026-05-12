# Tutor Solve-Rate Decay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В блоке «Решаемость по номерам» на дашборде репетитора показывать взвешенную решаемость по давности (забывание) и строить её по экзамену/формату, к которому готовится ученик.

**Architecture:** В `tutor_dashboard` выбираем предмет аналитики (`chart_subject_id`) → выбираем `ExamFormat` ученика (из `StudentSubjectProfile.exam_format`, fallback на активный формат по предмету) → считаем последнюю попытку по каждой задаче в рамках этого `ExamFormat`, применяем экспоненциальное затухание веса по age_days и агрегируем по номеру (`TaskType.number`).

**Tech Stack:** Django ORM, Django templates, Python math, unit tests (Django TestCase).

---

## Изменяемые файлы (map)

**Modify**
- `/workspace/core/views.py` — изменить расчёт `task_type_rates` в `tutor_dashboard`

**Create**
- `/workspace/core/tests/test_tutor_solve_rate_decay.py` — тесты на выбор `exam_format` + затухание веса

---

### Task 1: Написать падающий тест на выбор exam_format ученика и набор номеров

**Files:**
- Create: `/workspace/core/tests/test_tutor_solve_rate_decay.py`

- [ ] **Step 1: Write failing test**

```python
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, Subject, StudentSubjectProfile, Task, TaskType, TaskVariant, Topic, User


class TutorSolveRateDecayTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        self.subject = Subject.objects.create(name="Математика")
        self.ef_a = ExamFormat.objects.create(subject=self.subject, name="ОГЭ", year=2025, is_active=True)
        self.ef_b = ExamFormat.objects.create(subject=self.subject, name="ОГЭ", year=2026, is_active=False)

        # В ef_a будет только номер 1, в ef_b — номер 2 (проверим, что берётся ef_b из профиля)
        self.tt1 = TaskType.objects.create(exam_format=self.ef_a, number=1, name="N1", max_points=1)
        self.tt2 = TaskType.objects.create(exam_format=self.ef_b, number=2, name="N2", max_points=1)

        topic = Topic.objects.create(subject=self.subject, name="T")
        t = Task.objects.create(topic=topic, task_type=self.tt2, correct_answer="2", difficulty=50, exam_points=1)
        TaskVariant.objects.create(task=t, theme="classic", content="<p>U</p>", solution="<p>S</p>")

        StudentSubjectProfile.objects.create(student=self.student, subject=self.subject, exam_format=self.ef_b)

    def test_task_type_tiles_follow_student_exam_format(self):
        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"), {"student_id": self.student.id, "subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)

        # Должны быть плитки с номером 2 (из ef_b), а не только 1 (из ef_a)
        self.assertContains(res, ">2<")
        self.assertNotContains(res, ">1<")
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python manage.py test core.tests.test_tutor_solve_rate_decay.TutorSolveRateDecayTests -v 1
```
Expected: FAIL (пока `tutor_dashboard` берёт активный формат по предмету и/или не фильтрует по exam_format ученика).

- [ ] **Step 3: Commit failing test**

```bash
git add core/tests/test_tutor_solve_rate_decay.py
git commit -m "test: tutor solve-rate uses student exam format"
```

---

### Task 2: Реализовать выбор exam_format ученика для subject_id

**Files:**
- Modify: `/workspace/core/views.py`
- Test: `/workspace/core/tests/test_tutor_solve_rate_decay.py`

- [ ] **Step 1: Implement minimal code (GREEN)**

В `tutor_dashboard`, перед формированием `task_type_name_map` и `numbers`, добавить функцию/блок выбора формата:

```python
def _pick_student_exam_format(student, subject_id):
    profile = (
        StudentSubjectProfile.objects
        .filter(student=student, subject_id=subject_id)
        .select_related("exam_format", "subject")
        .first()
    )
    if profile and profile.exam_format_id:
        return profile.exam_format
    return (
        ExamFormat.objects.filter(subject_id=subject_id, is_active=True).order_by("-year", "name").first()
        or ExamFormat.objects.filter(subject_id=subject_id).order_by("-year", "name").first()
    )
```

И заменить текущий выбор `active_exam_format = ExamFormat.objects.filter(subject_id=chart_subject_id, is_active=True)...` на:

```python
active_exam_format = _pick_student_exam_format(selected_student, chart_subject_id) if selected_student else None
```

- [ ] **Step 2: Run test to verify it passes**

```bash
python manage.py test core.tests.test_tutor_solve_rate_decay.TutorSolveRateDecayTests::test_task_type_tiles_follow_student_exam_format -v 1
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add core/views.py
git commit -m "feat: use student exam format for tutor solve-rate tiles"
```

---

### Task 3: Падающий тест на «забывание» (half-life) и «последняя попытка по задаче»

**Files:**
- Modify: `/workspace/core/tests/test_tutor_solve_rate_decay.py`

- [ ] **Step 1: Add failing test**

```python
from core.models import Submission

    def test_rate_is_weighted_by_recency_and_uses_last_attempt_per_task(self):
        # setup: одна и та же задача — сначала верно давно, потом неверно сегодня.
        # должна учитываться только последняя попытка (сегодня, неверно) => rate около 0
        task = Task.objects.filter(task_type=self.tt2).first()
        now = timezone.now()
        old = now - timezone.timedelta(days=14)  # ровно half-life

        s_old = Submission.objects.create(student=self.student, task=task, user_answer="2", is_correct=True, score=1)
        Submission.objects.filter(id=s_old.id).update(created_at=old)
        s_new = Submission.objects.create(student=self.student, task=task, user_answer="1", is_correct=False, score=0)
        Submission.objects.filter(id=s_new.id).update(created_at=now)

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"), {"student_id": self.student.id, "subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)

        # Ищем плитку N2 и ожидаем "0%" (или очень близко)
        self.assertContains(res, ">2<")
        self.assertContains(res, "0%")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test core.tests.test_tutor_solve_rate_decay.TutorSolveRateDecayTests::test_rate_is_weighted_by_recency_and_uses_last_attempt_per_task -v 1
```
Expected: FAIL (пока rate считается грубо по всем submission и без last-attempt/decay).

- [ ] **Step 3: Commit failing test**

```bash
git add core/tests/test_tutor_solve_rate_decay.py
git commit -m "test: solve-rate decay and last-attempt behavior"
```

---

### Task 4: Реализовать взвешенную решаемость (decay) на основе последней попытки

**Files:**
- Modify: `/workspace/core/views.py`
- Test: `/workspace/core/tests/test_tutor_solve_rate_decay.py`

- [ ] **Step 1: Implement weighted aggregation**

В `tutor_dashboard` заменить блок:

```python
rows = Submission.objects.filter(student=selected_student)...
```

на расчёт, который:
1) фильтрует submission по выбранному exam_format:

```python
sub_qs = Submission.objects.filter(
    student=selected_student,
    task__task_type__exam_format=active_exam_format,
).exclude(task__task_type__number__isnull=True)
```

2) получает **последнюю попытку по каждой задаче** через `Subquery`:

```python
from django.db.models import OuterRef, Subquery

last_sub = (
    sub_qs.filter(task_id=OuterRef("task_id"))
    .order_by("-created_at")
)
last_created = Subquery(last_sub.values("created_at")[:1])
last_correct = Subquery(last_sub.values("is_correct")[:1])
```

3) строит “таблицу последних попыток” по task_id (без Postgres-only distinct):

```python
latest_rows = (
    sub_qs.values("task_id", "task__task_type__number")
    .annotate(last_created_at=last_created, last_is_correct=last_correct)
)
```

4) агрегирует в Python с half-life:

```python
import math
from django.utils import timezone

HALF_LIFE_DAYS = 14.0
today = timezone.localdate()

agg = {}  # number -> dict(weighted_total, weighted_correct, total_unique, correct_unique)
for r in latest_rows:
    n = int(r["task__task_type__number"])
    dt = r["last_created_at"]
    if not dt:
        continue
    age_days = max(0, (today - dt.date()).days)
    weight = 0.5 ** (age_days / HALF_LIFE_DAYS)
    is_corr = bool(r["last_is_correct"])
    a = agg.setdefault(n, {"wt": 0.0, "wc": 0.0, "total": 0, "correct": 0})
    a["wt"] += weight
    a["wc"] += weight * (1.0 if is_corr else 0.0)
    a["total"] += 1
    a["correct"] += 1 if is_corr else 0
```

И собрать `task_type_rates` по `numbers`:

```python
task_type_rates = []
for n in numbers:
    a = agg.get(int(n))
    if not a or a["wt"] <= 0:
        task_type_rates.append({"number": n, "name": task_type_name_map.get(n, ""), "rate": None, "total": 0, "correct": 0})
    else:
        rate = (a["wc"] / a["wt"]) * 100.0
        task_type_rates.append({"number": n, "name": task_type_name_map.get(n, ""), "rate": rate, "total": a["total"], "correct": a["correct"]})
```

- [ ] **Step 2: Run tests**

```bash
python manage.py test core.tests.test_tutor_solve_rate_decay -v 1
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add core/views.py
git commit -m "feat: weighted solve-rate with decay in tutor dashboard"
```

---

### Task 5: Регресс-тесты и прогон всего сьюта

**Files:**
- Test: `/workspace/core/tests/test_tutor_solve_rate_decay.py`

- [ ] **Step 1: Run full test suite**

```bash
python manage.py test core.tests -v 1
```
Expected: OK

- [ ] **Step 2: Push**

```bash
git push origin HEAD:main
```

---

## Self-review (plan vs spec)
- Spec «A» покрыта:
  - выбор `exam_format` ученика по предмету: Task 2
  - decay (half-life=14) + последняя попытка: Task 4
  - тесты на оба требования: Task 1 и Task 3
- Placeholder scan: в шагах нет TBD/TODO.

