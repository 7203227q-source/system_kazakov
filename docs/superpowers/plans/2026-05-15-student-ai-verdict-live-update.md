# Student assignment AI verdict live update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** После нажатия «Проверить через ИИ» на странице варианта ученика блок “Оценено/Вердикт ИИ” обновляется сразу без перезагрузки страницы.

**Architecture:**  
- В шаблоне всегда рендерим скрытый контейнер `ai_feedback_block_<taskId>` для задач с фото.  
- JS `verifyWithAI()` после успешного ответа заполняет заголовок/тело и показывает контейнер.  
- Добавляем smoke-тест на присутствие контейнера в HTML.

**Tech Stack:** Django templates + JS, Django TestCase.

---

## Map of changes (files)

**Modify:**
- `core/templates/core/student_solve_assignment.html`

**Create:**
- `core/tests/test_student_assignment_ai_block_present.py`

---

## Task 1: Test (RED) — контейнер блока ИИ всегда присутствует

**Files:**
- Create: `core/tests/test_student_assignment_ai_block_present.py`

- [ ] **Step 1: Write failing test**

```python
from django.test import TestCase

from core.models import User, Subject, ExamFormat, TaskType, Topic, Task, TaskVariant, Assignment


class StudentAssignmentAiBlockPresentTests(TestCase):
    def test_ai_feedback_block_container_present_for_extended_task(self):
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

        self.client.force_login(student)
        res = self.client.get(f"/student/assignment/{assignment.id}/")
        self.assertEqual(res.status_code, 200)

        html = res.content.decode("utf-8", errors="ignore")
        # контейнер должен присутствовать, даже если ai_feedback ещё нет
        self.assertIn(f'ai_feedback_block_{task.id}', html)
```

- [ ] **Step 2: Run test to verify RED**

```bash
python manage.py test core.tests.test_student_assignment_ai_block_present
```

---

## Task 2: Implementation (GREEN) — live-update контейнера в JS

**Files:**
- Modify: `core/templates/core/student_solve_assignment.html`
- Test: `core/tests/test_student_assignment_ai_block_present.py`

- [ ] **Step 1: Add hidden container in template**

Внутри карточки задания (в блоке где сейчас есть `ai-feedback-block`), добавить элементы:
- `div#ai_feedback_block_<taskId>` (class `ai-feedback-block hidden ...`)
- внутри:
  - `div#ai_feedback_title_<taskId>`
  - `div#ai_feedback_body_<taskId>`

Если `ai_feedback_display_html` уже есть — можно заполнить body сервером и снять hidden.

- [ ] **Step 2: Update verifyWithAI()**

В `verifyWithAI()` после успешного получения `data`:
- найти `blockEl/titleEl/bodyEl` по `taskId`
- собрать HTML:
  - если structured поля есть — отрендерить аналогично тому, как сейчас рендерится в `result_*`
  - иначе использовать `data.feedback_html`/`data.feedback`
- показать блок: `blockEl.classList.remove('hidden')`

- [ ] **Step 3: Run test**

```bash
python manage.py test core.tests.test_student_assignment_ai_block_present
```

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/student_solve_assignment.html core/tests/test_student_assignment_ai_block_present.py
git commit -m "feat(student): update AI verdict block without reload"
```

---

## Task 3: Full tests + merge

- [ ] **Step 1: Run full suite**
```bash
python manage.py test core.tests
```

- [ ] **Step 2: Merge**
```bash
git push origin HEAD
```
Then merge to `main` and push.

