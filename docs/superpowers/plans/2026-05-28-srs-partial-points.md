# SRS Partial Points for 2-Point Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В режиме интервального повторения (SRS) начислять 1 из 2 баллов за частично верный ответ по правилу “за каждый верный элемент по позициям”, даже если ответ короче эталона.

**Architecture:** Добавляем отдельную функцию подсчёта баллов только для SRS (`score_short_answer_srs`) и используем её в `student_practice` при `mode == "srs"`. “Официальный” скоринг (`score_short_answer`) для вариантов/проверок не меняем.

**Tech Stack:** Django, Python, unittest/Django TestCase, существующий модуль `core/scoring.py`.

---

## File Map

- Modify: `/workspace/core/scoring.py` — добавить `score_short_answer_srs(task, user_answer)`.
- Modify: `/workspace/core/views.py` — использовать SRS-скоринг только при `mode == "srs"`.
- Create: `/workspace/core/tests/test_srs_partial_points.py` — тесты на поведение только для SRS.

---

## Поведение (точные правила)

### Область применения

- Применяется только в `student_practice` при `mode == "srs"` для задач с `max_points == 2` и кратким ответом.
- Не влияет на:
  - проверку в вариантах (assignment)
  - endpoint `student_check_assignment_task`
  - любое другое место, где используется `score_short_answer`

### Правило частичного начисления для `max_points == 2`

Пусть:
- `correct = _normalize_digits_sequence(task.correct_answer)`
- `ans = _normalize_digits_sequence(user_answer)`

Тогда:
- если `ans == correct` и длины равны → `2`
- иначе посчитать `matches = sum(1 for i in range(min(len(ans), len(correct))) if ans[i] == correct[i])`
  - если `matches >= 1` → `1`
  - иначе → `0`

Примечания:
- Ввод длиннее эталона в SRS: возвращаем `0` (как и сейчас), чтобы не поощрять “дописал лишнего”.
- Для не-цифровых ответов (не последовательности цифр) — SRS не меняем: остаётся поведение `score_short_answer`.

---

### Task 1: Add Failing Tests (TDD)

**Files:**
- Create: `/workspace/core/tests/test_srs_partial_points.py`

- [ ] **Step 1: Write failing tests**

```python
from django.test import TestCase

from core.scoring import score_short_answer_srs
from core.models import ExamFormat, Subject, Task, TaskType, Topic


class SRSPartialPointsTests(TestCase):
    def test_2_point_sequence_shorter_answer_gets_1_point_if_first_digit_matches(self):
        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ физика (тест)", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=12, name="Тест (2 балла)", max_points=2, is_extended_answer=False)
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="2413", exam_points=2)

        self.assertEqual(score_short_answer_srs(task, "2"), 1)

    def test_2_point_sequence_shorter_answer_gets_0_if_no_positions_match(self):
        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ физика (тест)", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=12, name="Тест (2 балла)", max_points=2, is_extended_answer=False)
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="2413", exam_points=2)

        self.assertEqual(score_short_answer_srs(task, "9"), 0)

    def test_2_point_sequence_exact_match_gets_2(self):
        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ физика (тест)", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=12, name="Тест (2 балла)", max_points=2, is_extended_answer=False)
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="2413", exam_points=2)

        self.assertEqual(score_short_answer_srs(task, "2413"), 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python manage.py test core.tests.test_srs_partial_points -v 2
```

Expected: FAIL (например, `ImportError: cannot import name 'score_short_answer_srs'`).

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_srs_partial_points.py
git commit -m "test: add SRS partial points expectations"
```

---

### Task 2: Implement `score_short_answer_srs()`

**Files:**
- Modify: `/workspace/core/scoring.py`
- Test: `/workspace/core/tests/test_srs_partial_points.py`

- [ ] **Step 1: Add implementation**

Add near `score_short_answer`:

```python
def score_short_answer_srs(task, user_answer: str) -> int:
    max_points = int(get_max_points_effective(task) or 0)
    if max_points <= 0:
        return 0

    if max_points != 2:
        return score_short_answer(task, user_answer)

    correct_raw = (getattr(task, "correct_answer", "") or "").strip()
    ans_raw = (user_answer or "").strip()

    correct = _normalize_digits_sequence(correct_raw)
    ans = _normalize_digits_sequence(ans_raw)

    if not correct or not ans:
        return 0

    if len(ans) > len(correct):
        return 0

    if ans == correct and len(ans) == len(correct):
        return 2

    limit = min(len(ans), len(correct))
    matches = sum(1 for i in range(limit) if ans[i] == correct[i])
    return 1 if matches >= 1 else 0
```

- [ ] **Step 2: Run tests**

Run:

```bash
python manage.py test core.tests.test_srs_partial_points -v 2
```

Expected: PASS.

- [ ] **Step 3: Run existing scoring smoke tests**

Run:

```bash
python manage.py test core.tests.test_oge_physics_short_answer_points -v 2
```

Expected: PASS (мы не трогаем `score_short_answer`).

- [ ] **Step 4: Commit**

```bash
git add core/scoring.py
git commit -m "feat(srs): add partial points scoring for 2-point tasks"
```

---

### Task 3: Use SRS Scoring in `student_practice`

**Files:**
- Modify: `/workspace/core/views.py`
- Test: `/workspace/core/tests/test_srs_partial_points.py`

- [ ] **Step 1: Switch points calculation only for mode == 'srs'**

In `student_practice` POST branch replace:

```python
points_earned = score_short_answer(task, user_answer)
```

With:

```python
if mode == "srs":
    from core.scoring import score_short_answer_srs
    points_earned = score_short_answer_srs(task, user_answer)
else:
    points_earned = score_short_answer(task, user_answer)
```

- [ ] **Step 2: Run targeted tests**

Run:

```bash
python manage.py test core.tests.test_srs_partial_points -v 2
```

Expected: PASS.

- [ ] **Step 3: Optional integration smoke**

Run:

```bash
python manage.py test core.tests.test_student_practice_srs_mode_persists -v 2
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add core/views.py
git commit -m "feat(srs): use SRS-only short answer scoring"
```

---

## Plan Self-Review

- Spec coverage: реализован SRS-only подсчёт с частичным баллом за совпадения по позициям, без изменения официального скоринга.
- Placeholder scan: нет TODO/TBD, все шаги с точными путями, кодом и командами.
- Type consistency: функция `score_short_answer_srs(task, user_answer: str)` используется только в `student_practice` при `mode == "srs"`.

