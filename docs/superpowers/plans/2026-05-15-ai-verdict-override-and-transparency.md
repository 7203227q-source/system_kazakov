# AI Verdict Visibility + Tutor Override + Prompt Tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Репетитор может исправлять оценку ИИ и в варианте, и в журнале; ученик в варианте видит полный отчёт ИИ (распознанное решение/ошибки/вердикт); prompt проверки по фото “мягко” запрещает додумывание и требует явной маркировки неуверенности.

**Architecture:**  
- UI override в `tutor_student_history.html` использует существующий endpoint `/api/tutor/submission/<id>/override-score/`.  
- В `student_solve_assignment` view добавляем подготовку `ai_mistakes/ai_verdict/ai_feedback_display_html` и выводим полный блок ИИ в шаблоне.  
- В `verifyWithAI` правим prompt: “описывай только видимое”, помечай сомнения, добавь секцию про неуверенность в verdict.

**Tech Stack:** Django (views/templates), небольшие JS handlers, Django TestCase.

---

## Map of changes (files)

**Modify:**
- `core/templates/core/tutor_student_history.html` — UI override-score для каждого submission
- `core/templates/core/student_solve_assignment.html` — полный блок “Фото и вердикт ИИ” (recognized_solution/mistakes/verdict)
- `core/views.py` — подготовка структурных полей для student_solve_assignment; правка prompt в verifyWithAI

**Create:**
- `core/tests/test_student_assignment_ai_full_report.py`
- `core/tests/test_tutor_history_override_ui_smoke.py`

---

## Task 1: Tests (RED) — ученик видит полный отчёт ИИ в варианте

**Files:**
- Create: `core/tests/test_student_assignment_ai_full_report.py`

- [ ] **Step 1: Write failing test**

```python
import json

from django.test import TestCase

from core.models import (
    User,
    Subject,
    ExamFormat,
    TaskType,
    Topic,
    Task,
    TaskVariant,
    Assignment,
    Submission,
)


class StudentAssignmentAiFullReportTests(TestCase):
    def test_student_assignment_shows_recognized_solution_mistakes_verdict(self):
        tutor = User.objects.create_user(username="t1", password="pw", role="tutor")
        student = User.objects.create_user(username="s1", password="pw", role="student")
        tutor.students.add(student)

        subject = Subject.objects.create(name="Физика")
        ef = ExamFormat.objects.create(subject=subject, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=25, name="Развёрнутая", max_points=3, is_extended_answer=True)
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="", exam_points=3)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        assignment = Assignment.objects.create(tutor=tutor, student=student, title="Вариант", is_draft=False, is_deleted=False)
        assignment.tasks.add(task)

        sub = Submission.objects.create(
            student=student,
            assignment=assignment,
            task=task,
            user_answer="",
            is_correct=False,
            primary_score=1,
            score=1,
            ai_feedback="Коротко",
            ai_recognized_solution="Распознано: x=1",
            ai_mistakes_json=json.dumps(["Ошибка 1"], ensure_ascii=False),
            ai_verdict_json=json.dumps(["Вердикт 1"], ensure_ascii=False),
        )

        self.client.force_login(student)
        res = self.client.get(f"/student/assignment/{assignment.id}/")
        self.assertEqual(res.status_code, 200)

        self.assertContains(res, "Фото и вердикт ИИ")
        self.assertContains(res, "Решение (как распознано)")
        self.assertContains(res, "Распознано: x=1")
        self.assertContains(res, "Ошибка 1")
        self.assertContains(res, "Вердикт 1")
```

- [ ] **Step 2: Run test to verify RED**

```bash
python manage.py test core.tests.test_student_assignment_ai_full_report
```

---

## Task 2: Implement full AI report in student assignment (GREEN)

**Files:**
- Modify: `core/views.py` (`student_solve_assignment`)
- Modify: `core/templates/core/student_solve_assignment.html`
- Test: `core/tests/test_student_assignment_ai_full_report.py`

- [ ] **Step 1: Prepare ai_mistakes / ai_verdict / ai_feedback_display_html for saved submissions**

In `core/views.py` inside `student_solve_assignment`, after tasks/submissions are attached, ensure for every `task.saved_submission`:
- parse JSON fields:
```python
task.saved_submission.ai_mistakes = pyjson.loads(task.saved_submission.ai_mistakes_json) if task.saved_submission.ai_mistakes_json else []
task.saved_submission.ai_verdict = pyjson.loads(task.saved_submission.ai_verdict_json) if task.saved_submission.ai_verdict_json else []
```
- prepare sanitized HTML (reuse existing logic already present for `ai_feedback_display_html`; if it’s only in one branch — move/reuse so it runs consistently).

- [ ] **Step 2: Add expandable block “Фото и вердикт ИИ” in template**

In `core/templates/core/student_solve_assignment.html` inside each task card, add:
- button: “Фото и вердикт ИИ”
- hidden panel showing:
  - image_url / image_url_2 if present
  - ai_recognized_solution
  - ai_mistakes list
  - ai_verdict list
  - ai_feedback_display_html as “Коротко” (optional)

Use same UI copy as in spec:
“Решение (как распознано)”, “Ошибки и замечания”, “Итоговый вердикт”.

- [ ] **Step 3: Run test to verify GREEN**

```bash
python manage.py test core.tests.test_student_assignment_ai_full_report
```

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/templates/core/student_solve_assignment.html core/tests/test_student_assignment_ai_full_report.py
git commit -m "feat(student): show full AI report in assignment"
```

---

## Task 3: Tutor override score UI in tutor journal

**Files:**
- Modify: `core/templates/core/tutor_student_history.html`
- Create: `core/tests/test_tutor_history_override_ui_smoke.py`

- [ ] **Step 1: Write smoke test (RED)**

```python
from django.test import TestCase
from core.models import User, Subject, Topic, Task, TaskVariant, Submission


class TutorHistoryOverrideUiSmokeTests(TestCase):
    def test_override_ui_present_in_tutor_history(self):
        tutor = User.objects.create_user(username="t1", password="pw", role="tutor")
        student = User.objects.create_user(username="s1", password="pw", role="student")
        tutor.students.add(student)

        subject = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, correct_answer="1", exam_points=3)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        Submission.objects.create(student=student, task=task, user_answer="", is_correct=False, primary_score=1, score=1)

        self.client.force_login(tutor)
        res = self.client.get(f"/tutor/student/{student.id}/history/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Баллы репетитора")
```

- [ ] **Step 2: Implement UI + JS handler**

In `core/templates/core/tutor_student_history.html`, within each submission block:
- show effective score (tutor override if exists)
- add numeric input + button
- add JS function `tutorOverrideScore(submissionId, maxPoints)` that POSTs to `/api/tutor/submission/<id>/override-score/` with `tutor_primary_score`
- after success: `location.reload()`

- [ ] **Step 3: Run test**

```bash
python manage.py test core.tests.test_tutor_history_override_ui_smoke
```

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/tutor_student_history.html core/tests/test_tutor_history_override_ui_smoke.py
git commit -m "feat(tutor): override AI score from history"
```

---

## Task 4: Prompt tuning (soft anti-hallucination)

**Files:**
- Modify: `core/views.py` (verifyWithAI / OpenRouter prompt)

- [ ] **Step 1: Update prompt text**

In the prompt block (where we request JSON fields), insert rules:
- “Опирайся только на то, что реально видно на фото”
- “Если не читается/не видно — явно пиши [неразборчиво]/[не видно]/[сомнение]”
- “Не добавляй шаги решения без пометки ‘предположил(а)’”
- In `verdict` require a paragraph: “Неуверенность распознавания”

No DB changes needed.

- [ ] **Step 2: Commit**

```bash
git add core/views.py
git commit -m "chore(ai): reduce hallucinations in photo grading prompt"
```

---

## Task 5: Full test run + merge

- [ ] **Step 1: Run full suite**
```bash
python manage.py test core.tests
```

- [ ] **Step 2: Push branch + merge to main**
```bash
git push origin HEAD
```
Then merge to `main` and push.

