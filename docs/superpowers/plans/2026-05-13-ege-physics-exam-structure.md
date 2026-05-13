# ЕГЭ физика: структура + флаг развёрнутой части — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить `TaskType.is_extended_answer` и заполнить/обновить структуру ЕГЭ физики (1–26, баллы, части), чтобы 1–20 решались без фото, а 21–26 — с фото и ИИ‑проверкой.

**Architecture:** Явный флаг `TaskType.is_extended_answer` определяет “развёрнутость” (фото/ИИ), вместо эвристики `max_points>1`. Данные проставляем миграцией (physics split_after=20), одновременно обновляя существующие экзамены (ОГЭ/ЕГЭ матем).

**Tech Stack:** Django models+migrations, Django views, Django templates, Django TestCase.

---

## Files (map)

**Modify**
- `/workspace/core/models.py` — добавить поле `TaskType.is_extended_answer`
- `/workspace/core/views.py` — `student_solve_assignment`, `api_verify_with_ai`, `student_assignment_summary`

**Create**
- `/workspace/core/migrations/00xx_tasktype_is_extended_answer.py`
- `/workspace/core/migrations/00xy_seed_ege_physics_tasktypes.py`
- `/workspace/core/tests/test_ege_physics_structure.py`

---

### Task 1: RED — тесты логики “часть 1/2” для ЕГЭ физики

**Files:**
- Create: `/workspace/core/tests/test_ege_physics_structure.py`

- [ ] **Step 1: Write failing tests**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, Submission, User


class EGEPhysicsStructureTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        self.physics = Subject.objects.create(name="Физика")
        self.ef = ExamFormat.objects.create(subject=self.physics, name="ЕГЭ физика", year=2026, is_active=True)
        topic = Topic.objects.create(subject=self.physics, name="T")

        # Тестовая задача на 2 балла (часть 1)
        self.tt_test2 = TaskType.objects.create(exam_format=self.ef, number=6, name="Тест (2 балла)", max_points=2, is_extended_answer=False)
        self.task_test2 = Task.objects.create(topic=topic, task_type=self.tt_test2, correct_answer="1", difficulty=10, exam_points=2)

        # Развёрнутая задача (часть 2)
        self.tt_ext = TaskType.objects.create(exam_format=self.ef, number=21, name="Развёрнутая", max_points=3, is_extended_answer=True)
        self.task_ext = Task.objects.create(topic=topic, task_type=self.tt_ext, correct_answer="1", difficulty=10, exam_points=3)

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=self.ef)
        self.assignment.tasks.add(self.task_test2, self.task_ext)

    def test_part1_2points_does_not_require_photo(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        # Для тестовой задачи должен быть input ответа
        self.assertContains(res, f'name=\"answer_{self.task_test2.id}\"')

    def test_finish_requires_photo_only_for_extended(self):
        self.client.login(username="s", password="pass")
        # Создаём сабмишн для развёрнутой без фото → finish должен редиректнуть обратно, не 500
        Submission.objects.create(student=self.student, assignment=self.assignment, task=self.task_ext)
        res = self.client.post(
            reverse("student_solve_assignment", args=[self.assignment.id]),
            data={"action": "finish", f"answer_{self.task_test2.id}": "1"},
            follow=False,
        )
        self.assertIn(res.status_code, (302, 303))
```

- [ ] **Step 2: Run to verify fails**

```bash
python manage.py test core.tests.test_ege_physics_structure -v 1
```

- [ ] **Step 3: Commit failing tests**

```bash
git add core/tests/test_ege_physics_structure.py
git commit -m "test: ege physics part split uses explicit extended flag"
```

---

### Task 2: GREEN — добавить поле TaskType.is_extended_answer + миграция

**Files:**
- Modify: `/workspace/core/models.py`
- Create: `/workspace/core/migrations/00xx_tasktype_is_extended_answer.py`
- Test: `/workspace/core/tests/test_ege_physics_structure.py`

- [ ] **Step 1: Update model**

```python
class TaskType(models.Model):
    ...
    is_extended_answer = models.BooleanField(default=False, verbose_name="Развёрнутый ответ (требует фото)")
```

- [ ] **Step 2: makemigrations**

```bash
python manage.py makemigrations core
```

- [ ] **Step 3: Run tests (should still fail — логика ещё старая)**

```bash
python manage.py test core.tests.test_ege_physics_structure -v 1
```

- [ ] **Step 4: Commit**

```bash
git add core/models.py core/migrations
git commit -m "feat: add TaskType.is_extended_answer"
```

---

### Task 3: GREEN — сид данных: ЕГЭ физика TaskType 1–26 + backfill для математики

**Files:**
- Create: `/workspace/core/migrations/00xy_seed_ege_physics_tasktypes.py`

- [ ] **Step 1: Create data migration**
В `forwards()`:
1) Найти `ExamFormat` “ЕГЭ физика” (year=2026) и создать/обновить `TaskType` 1..26:
   - `number` = 1..26
   - `name` = короткое “Задание №N”
   - `max_points` выставить согласно распределению (часть 2 точно: 21=3,22=2,23=2,24=3,25=3,26=4; часть 1 — 1 или 2 по актуальной схеме)
   - `is_extended_answer = (number > 20)`
2) Backfill:
   - если формат “ОГЭ математика”: `number > 19`
   - если “ЕГЭ математика”: `number > 12`

- [ ] **Step 2: Commit**

```bash
git add core/migrations/00xy_seed_ege_physics_tasktypes.py
git commit -m "feat: seed ege physics task types and backfill extended flag"
```

---

### Task 4: GREEN — обновить логику приложения на is_extended_answer

**Files:**
- Modify: `/workspace/core/views.py`

- [ ] **Step 1: student_solve_assignment**
Заменить проверки `max_points_effective > 1` на:
`bool(task.task_type and task.task_type.is_extended_answer)`
в местах:
- пропуск обработки ответа при POST (для развёрнутых не затирать результаты),
- блок “missing_part2” при finish,
- выставление `task.needs_photo` (часть 2 = extended).

- [ ] **Step 2: api_verify_with_ai**
Заменить `max_points <= 1` проверкой:
`if not task.task_type or not task.task_type.is_extended_answer: return only_second_part`.
`max_points` оставить для шкалы.

- [ ] **Step 3: student_assignment_summary**
Определять начисление баллов по `is_extended_answer`, а не по `task.exam_points == 1`.

- [ ] **Step 4: Run tests**

```bash
python manage.py test core.tests.test_ege_physics_structure -v 1
python manage.py test core.tests -v 1
```

- [ ] **Step 5: Commit**

```bash
git add core/views.py
git commit -m "fix: use explicit extended flag instead of max_points heuristic"
```

---

### Task 5: Push

- [ ] **Step 1: Push**

```bash
git push origin main
```

