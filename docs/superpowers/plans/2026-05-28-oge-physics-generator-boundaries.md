# OGE Physics Generator Boundaries (1–16 / 17–...) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** На странице создания варианта для ОГЭ по физике показывать корректные границы частей: тестовая часть 1–16, развёрнутая часть 17–…, если в данных проставлен `TaskType.is_extended_answer`.

**Architecture:** В `tutor_create_assignment` убрать “подозрительную” эвристику `suspicious_physics`, которая форсит разбиение 1–20/21–… для любого формата физики. Вместо этого применять fallback только когда разметка частей отсутствует/неконсистентна (нет part2 или пересечение границ), а если флаги `is_extended_answer` уже есть — доверять им.

**Tech Stack:** Django, Django TestCase, существующий генератор в `core/views.py`.

---

## File Map

- Modify: `/workspace/core/views.py` — `tutor_create_assignment` (расчёт `part1_max/part2_min`).
- Modify: `/workspace/core/tests/test_exam_structure_boundaries_in_generator.py` — расширить/скорректировать ожидания под ОГЭ физику.

---

## Текущая проблема

В `tutor_create_assignment` после вычисления границ по `TaskType.is_extended_answer` включается эвристика `suspicious_physics`, и для физики принудительно выставляется “1–20 / 21–max”, что неверно для ОГЭ физики.

---

## Новое правило (Design A)

1) Если в формате есть и `is_extended_answer=False`, и `is_extended_answer=True` (т.е. обе части определены данными):
- использовать границы по данным:
  - `part1_max = max(number where is_extended_answer=False)`
  - `part2_min = min(number where is_extended_answer=True)`
  - `part2_max = max(number where is_extended_answer=True)`
- не применять fallback по физике

2) Fallback применять только если разметка неполная или неконсистентная:
- отсутствует `part1_max` или отсутствует `part2_min`, или `part2_min <= part1_max`
  - тогда использовать существующую fallback-логику (в т.ч. 1–20/21–… для физики, если она нужна для ЕГЭ/сломанных данных)

---

### Task 1: Add/Adjust Tests (TDD)

**Files:**
- Modify: `/workspace/core/tests/test_exam_structure_boundaries_in_generator.py`

- [ ] **Step 1: Add test for OGE physics boundaries (1–16)**

Add a new test case (or extend existing) that creates:
- `Subject(name="Физика")`
- `ExamFormat(name` содержит `"ОГЭ"`, `year=2026`, `is_active=True)`
- TaskTypes `1..22` where `1..16 is_extended_answer=False`, `17..22 is_extended_answer=True`

Then request the generator page and assert that:
- “Тестовая часть” ends at 16
- “Развернутая часть” starts at 17

Concrete snippet to add:

```python
def test_generator_boundaries_oge_physics_respects_is_extended_answer_split_16(self):
    from django.urls import reverse
    from core.models import ExamFormat, Subject, TaskType, User

    tutor = User.objects.create_user(username="t", password="pw", role="tutor")
    self.client.force_login(tutor)

    subject = Subject.objects.create(name="Физика")
    ef = ExamFormat.objects.create(subject=subject, name="ОГЭ физика (тест)", year=2026, is_active=True)

    for n in range(1, 23):
        TaskType.objects.create(
            exam_format=ef,
            number=n,
            name=f"№{n}",
            max_points=1,
            is_extended_answer=(n >= 17),
        )

    res = self.client.get(reverse("tutor_create_assignment"), {"exam_format_id": ef.id})
    self.assertEqual(res.status_code, 200)

    # Эти строки зависят от шаблона, поэтому проверяем по фактическим значениям в контексте:
    self.assertEqual(res.context["part1_max"], 16)
    self.assertEqual(res.context["part2_min"], 17)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python manage.py test core.tests.test_exam_structure_boundaries_in_generator -v 2
```

Expected: FAIL (сейчас `part1_max` становится 20 из-за fallback).

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_exam_structure_boundaries_in_generator.py
git commit -m "test: OGE physics generator boundaries should end at 16"
```

---

### Task 2: Fix `tutor_create_assignment` Boundaries Logic

**Files:**
- Modify: `/workspace/core/views.py`
- Test: `/workspace/core/tests/test_exam_structure_boundaries_in_generator.py`

- [ ] **Step 1: Update suspicious/fallback condition**

In `tutor_create_assignment` (search for `suspicious_physics`), replace the condition so that fallback applies only when:
- `part1_max` is missing, or `part2_min` is missing, or `part2_min <= part1_max`

Example patch logic (exact placement to match surrounding code):

```python
has_part1 = bool(guessed_part1_max)
has_part2 = bool(guessed_part2_min)
invalid_split = bool(has_part1 and has_part2 and int(guessed_part2_min) <= int(guessed_part1_max))

suspicious_physics = is_physics and (not has_part1 or not has_part2 or invalid_split)
```

This ensures that for OGE physics with full split (1–16, 17–22) we do NOT fallback to 1–20.

- [ ] **Step 2: Run tests**

Run:

```bash
python manage.py test core.tests.test_exam_structure_boundaries_in_generator -v 2
```

Expected: PASS.

- [ ] **Step 3: Optional smoke for create assignment UI**

Run:

```bash
python manage.py test core.tests.test_tutor_create_assignment_dynamic_exam_format -v 2
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add core/views.py
git commit -m "fix(generator): respect OGE physics part split from task types"
```

---

## Plan Self-Review

- Spec coverage: устраняет неверное разбиение 1–20 для ОГЭ физики на странице генератора, сохраняя fallback только для действительно неконсистентных данных.
- Placeholder scan: отсутствуют TODO/TBD, команды и код указаны.
- Consistency: ориентируемся на `TaskType.is_extended_answer` как на источник истины (как в админке структуры).

