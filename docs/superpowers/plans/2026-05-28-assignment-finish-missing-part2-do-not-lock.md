# Assignment Finish: Missing Part2 Should Not Lock Test Answers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Если ученик нажимает «Завершить вариант», но по заданиям 2-й части нет фото, система показывает предупреждение и кнопку «Завершить всё равно», при этом ответы тестовой части остаются редактируемыми (не становятся readonly).

**Architecture:** В `student_solve_assignment` при `action == "finish"` и `force_finish != 1` сначала проверяем, есть ли незагруженные фото по 2-й части. Если да — сохраняем введённые ответы тестовой части как черновики (`user_answer`), но не выставляем `is_correct` (оставляем `None`) и возвращаем страницу с `needs_force_finish=True`. Финальная проверка/лок происходит только после `force_finish=1` или при отсутствии пропусков по 2-й части.

**Tech Stack:** Django, Django templates, Django TestCase.

---

## File Map

- Modify: `/workspace/core/views.py` — изменить `student_solve_assignment` (POST finish flow).
- Create: `/workspace/core/tests/test_assignment_finish_missing_part2_does_not_lock.py` — регрессионный тест на сценарий.

---

## Регрессионный сценарий (что фиксируем)

1) У варианта есть:
- 1 задача тестовой части (`is_extended_answer=False`)
- 1 задача 2-й части (`is_extended_answer=True`) без `image_url`

2) Ученик нажимает «Завершить вариант»:
- сервер показывает предупреждение (needs_force_finish=True)
- введённый ответ тестовой части сохраняется как `Submission.user_answer`
- но `Submission.is_correct` для тестовой части остаётся `None`
- на странице поле ответа НЕ `readonly`

3) После того как ученик нажимает «Завершить всё равно» (`force_finish=1`):
- вариант завершается (редирект на summary)
- для тестовой части выставляется `is_correct` и `score` (как раньше)

---

### Task 1: Add Failing Regression Test (TDD)

**Files:**
- Create: `/workspace/core/tests/test_assignment_finish_missing_part2_does_not_lock.py`

- [ ] **Step 1: Write failing test**

```python
from django.test import TestCase
from django.urls import reverse

from bs4 import BeautifulSoup

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class AssignmentFinishMissingPart2DoesNotLockTests(TestCase):
    def test_finish_with_missing_part2_preserves_drafts_and_keeps_input_editable(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")

        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ОГЭ", year=2026, is_active=True)

        tt_test = TaskType.objects.create(exam_format=ef, number=1, name="Тест", max_points=1, is_extended_answer=False)
        tt_part2 = TaskType.objects.create(exam_format=ef, number=19, name="Часть 2", max_points=2, is_extended_answer=True)

        topic = Topic.objects.create(subject=subject, name="T")
        task_test = Task.objects.create(topic=topic, task_type=tt_test, correct_answer="2", difficulty=50, exam_points=1)
        task_part2 = Task.objects.create(topic=topic, task_type=tt_part2, correct_answer="", difficulty=50, exam_points=2)

        TaskVariant.objects.create(task=task_test, theme="classic", content="<p>U</p>", solution="<p>S</p>")
        TaskVariant.objects.create(task=task_part2, theme="classic", content="<p>U2</p>", solution="<p>S2</p>")

        assignment = Assignment.objects.create(tutor=tutor, student=student, title="A", is_draft=False)
        assignment.tasks.add(task_test, task_part2)

        self.client.login(username="s", password="pass")

        url = reverse("student_solve_assignment", args=[assignment.id])

        res = self.client.post(
            url,
            {
                "action": "finish",
                f"answer_{task_test.id}": "2",
            },
            follow=True,
        )

        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Не все задания 2-й части сданы")
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_completed)

        sub_test = Submission.objects.get(student=student, assignment=assignment, task=task_test)
        self.assertEqual(sub_test.user_answer, "2")
        self.assertIsNone(sub_test.is_correct)

        soup = BeautifulSoup(res.content, "html.parser")
        inp = soup.find("input", {"id": f"answer_{task_test.id}"})
        self.assertIsNotNone(inp)
        self.assertFalse(inp.has_attr("readonly"))
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python manage.py test core.tests.test_assignment_finish_missing_part2_does_not_lock -v 2
```

Expected: FAIL (в текущем поведении `is_correct` становится `False`, а `readonly` появляется).

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_assignment_finish_missing_part2_does_not_lock.py
git commit -m "test: regression for finish with missing part2 not locking answers"
```

---

### Task 2: Change Finish Flow to Not Lock Before Force-Finish

**Files:**
- Modify: `/workspace/core/views.py`
- Test: `/workspace/core/tests/test_assignment_finish_missing_part2_does_not_lock.py`

- [ ] **Step 1: Implement early missing_part2 check**

In `student_solve_assignment`, inside POST branch and after `action` validation:

1) Compute `force_finish`:

```python
force_finish = (request.POST.get("force_finish") == "1")
```

2) If `action == "finish"` and not `force_finish`, check missing part2 without mutating test submissions:
- ensure `Submission` exists for extended tasks (it is already created in `_render_student_solve_assignment` for tasks needing photo, but we should not rely on GET having happened)
- treat missing as `not sub.image_url`

3) If missing part2 exists:
- for every non-extended task: save `user_answer` into `Submission` with `is_correct=None` exactly like postpone branch (only update if `sub.is_correct is None`)
- return `_render_student_solve_assignment(needs_force_finish=True, missing_part2_tasks=missing_part2)` after `messages.warning(...)`

4) If not missing OR `force_finish == True`, proceed with existing loop and current logic, but remove duplicated missing_part2 check at the end to avoid double-work.

- [ ] **Step 2: Run the new regression test**

Run:

```bash
python manage.py test core.tests.test_assignment_finish_missing_part2_does_not_lock -v 2
```

Expected: PASS.

- [ ] **Step 3: Run existing lock tests**

Run:

```bash
python manage.py test core.tests.test_assignment_answer_lock -v 2
```

Expected: PASS (механизм readonly после обычной проверки должен сохраниться).

- [ ] **Step 4: Commit**

```bash
git add core/views.py
git commit -m "fix(assignment): do not lock test answers before force-finish"
```

---

## Plan Self-Review

- Spec coverage: правка исключает проставление `is_correct` в промежуточном экране предупреждения, сохраняя при этом введённые ответы как черновики.
- Placeholder scan: нет TODO/TBD, указаны конкретные тесты и команды.
- Consistency: `readonly` в шаблоне зависит от `is_correct != None`, поэтому решение удерживает `is_correct=None` до подтверждения.

