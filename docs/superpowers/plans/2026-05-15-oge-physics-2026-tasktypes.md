# OGE Physics 2026 task types Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить поддержку ОГЭ Физика 2026: корректные `TaskType.max_points`, названия типов, и корректное разделение на тестовую/развёрнутую часть (не по баллам, а по флагу `TaskType.is_extended_answer`).

**Architecture:** 1) Вводим поле `TaskType.is_extended_answer`. 2) Миграцией сидим ОГЭ физику 2026 (ExamFormat + TaskType 1..22) и бэкфилим флаг для существующих ОГЭ (по подстроке в имени). 3) В `student_solve_assignment` и `student_assignment_summary` используем этот флаг для логики «нужно фото/как считать баллы».

**Tech Stack:** Django + data migrations.

---

## Map of changes (files)

**Modify:**
- `core/models.py` — поле `TaskType.is_extended_answer`
- `core/views.py` — логика «часть 2» и подсчёта первичных баллов

**Create:**
- `core/migrations/0024_tasktype_is_extended_answer_and_seed_oge_physics_2026.py`
- `core/tests/test_oge_physics_part2_logic.py`

---

## Task 1: TDD — тест на корректную «часть 2» (не по exam_points)

**Files:**
- Create: `core/tests/test_oge_physics_part2_logic.py`

- [ ] **Step 1: Write failing test**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Subject, ExamFormat, TaskType, Topic, Task, TaskVariant, User, Assignment


class OGEPhysicsPart2LogicTests(TestCase):
    def test_short_answer_2_points_is_not_part2(self):
        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="Тест 2 балла", max_points=2)
        # Важно: exam_points=2, но это тестовая часть
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", exam_points=2)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        student = User.objects.create_user(username="s1", password="pw", role="student")
        assignment = Assignment.objects.create(tutor=student, student=student, title="Вариант")
        assignment.tasks.add(task)

        self.client.force_login(student)
        res = self.client.get(reverse("student_solve_assignment", args=[assignment.id]))
        self.assertEqual(res.status_code, 200)

        # Если логика была "exam_points > 1", то показывался бы QR/блок фото.
        # Проверяем, что upload_token не создан (т.е. фото не требуется).
        self.assertNotContains(res, "upload_token")
```

- [ ] **Step 2: Run test to verify RED**

Run:
```bash
python manage.py test core.tests.test_oge_physics_part2_logic
```

- [ ] **Step 3: Implement minimal fix in views using TaskType.is_extended_answer**

В `student_solve_assignment` заменить:
```python
is_part2 = task.exam_points > 1
```
на:
```python
is_part2 = bool(getattr(getattr(task, "task_type", None), "is_extended_answer", False))
if task.task_type_id is None:
    is_part2 = task.exam_points > 1
```

- [ ] **Step 4: Re-run test to verify GREEN**

Run:
```bash
python manage.py test core.tests.test_oge_physics_part2_logic
```

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/tests/test_oge_physics_part2_logic.py
git commit -m "fix(oge): determine part2 by task type flag, not points"
```

---

## Task 2: Модель + миграция: is_extended_answer + сидинг ОГЭ Физика 2026

**Files:**
- Modify: `core/models.py`
- Create: `core/migrations/0024_tasktype_is_extended_answer_and_seed_oge_physics_2026.py`

- [ ] **Step 1: Add field to TaskType model**

```python
is_extended_answer = models.BooleanField(default=False, verbose_name="Развёрнутый ответ (часть 2)")
```

- [ ] **Step 2: Create migration**

Migration должен:
1) добавить поле `is_extended_answer` в `TaskType`;
2) проставить `is_extended_answer=True` для существующих `TaskType`, где `name` содержит `развёрнутый ответ`;
3) создать/обновить `Subject(Физика)` + `ExamFormat(ОГЭ, 2026)` + `TaskType` 1..22 с `max_points` и `is_extended_answer` по таблице спеки.

- [ ] **Step 3: Migrate + verify**

Run:
```bash
python manage.py migrate
```

- [ ] **Step 4: Commit**

```bash
git add core/models.py core/migrations
git commit -m "feat(oge): add extended-answer flag and seed physics 2026 task types"
```

---

## Task 3: Исправить подсчёт первичных баллов в итогах варианта

**Files:**
- Modify: `core/views.py`

- [ ] **Step 1: Update scoring in student_assignment_summary**

Заменить ветвление `if task.exam_points == 1` на:
```python
is_part2 = bool(getattr(getattr(task, \"task_type\", None), \"is_extended_answer\", False))
if not is_part2:
    points_earned = task.exam_points if sub.is_correct else 0
else:
    points_earned = sub.primary_score or 0
```

Аналогично заменить расчёт `student_primary` в `student_solve_assignment` (POST).

- [ ] **Step 2: Add/adjust test (optional extension)**
При необходимости расширить тест из Task 1: сделать POST и проверить, что `total_primary_earned` учитывает 2 балла.

- [ ] **Step 3: Commit**

```bash
git add core/views.py
git commit -m "fix(oge): correct primary score calc for 2-point short answers"
```

---

## Task 4: Regression + merge

- [ ] **Step 1: Run test suite**

```bash
python manage.py test core.tests
```

- [ ] **Step 2: Merge to main and push**

```bash
git checkout main
git pull --ff-only origin main
git merge --no-ff feat/oge-physics-2026-tasktypes -m "feat(oge): physics 2026 task types"
git push origin main
```

