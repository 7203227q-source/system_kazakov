# Assignment Title Generation + Preview Focus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** При создании варианта автогенерировать заголовок в формате “экзамен → ученик → тип + №”, а при замене задачи в предпросмотре автоматически скроллить к новой задаче.

**Architecture:** В `Assignment` сохраняем `kind` и `student_seq`. При POST в `tutor_create_assignment` если `title` пустой — вычисляем `student_seq = max+1` по ученику и собираем `title` с префиксом `exam_format`. При `tutor_regenerate_task` редиректим на preview с `focus_task_id`, а preview-страница скроллит к `#task-<id>`.

**Tech Stack:** Django models/migrations, Django views/templates, Django TestCase.

---

## Files (map)

**Modify**
- `/workspace/core/models.py` — добавить поля `Assignment.kind`, `Assignment.student_seq`
- `/workspace/core/migrations/` — новая миграция добавляющая поля
- `/workspace/core/views.py` — `tutor_create_assignment` (автоген title + seq + kind), `tutor_regenerate_task` (focus_task_id)
- `/workspace/core/templates/core/tutor_create_assignment.html` — перестановка полей + select “Тип варианта”
- `/workspace/core/templates/core/tutor_preview_assignment.html` — `id="task-{{ task.id }}"` + JS focus

**Create**
- `/workspace/core/tests/test_assignment_title_autogen.py`
- `/workspace/core/tests/test_tutor_regenerate_task_focus.py`

---

### Task 1: RED — тест автогенерации названия + student_seq

**Files:**
- Create: `/workspace/core/tests/test_assignment_title_autogen.py`

- [ ] **Step 1: Write failing test**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, StudentSubjectProfile, Subject, Task, TaskType, Topic, User


class AssignmentTitleAutogenTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        self.ef = ExamFormat.objects.create(subject=subj, name="ОГЭ математика", year=2026, is_active=True)
        StudentSubjectProfile.objects.create(student=self.student, subject=subj, exam_format=self.ef)

        tt = TaskType.objects.create(exam_format=self.ef, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subj, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)

    def _post(self):
        return self.client.post(
            reverse("tutor_create_assignment"),
            {
                "student_id": str(self.student.id),
                "exam_format": str(self.ef.id),
                "kind": "homework",
                "title": "",
                f"type_count_{self.task.task_type_id}": "1",
                "subtype_checked_1": "on",
                "subtype_name_1": self.task.subtype_tag or "",
                "subtype_type_1": str(self.task.task_type_id),
            },
        )

    def test_autogen_title_prefix_and_seq(self):
        self.client.login(username="t", password="pass")
        res = self._post()
        self.assertEqual(res.status_code, 302)

        a = Assignment.objects.latest("id")
        self.assertEqual(a.student_id, self.student.id)
        self.assertEqual(a.exam_format_id, self.ef.id)
        self.assertEqual(a.kind, "homework")
        self.assertEqual(a.student_seq, 1)
        self.assertTrue(a.title.startswith("ОГЭ математика 2026 — "))
        self.assertIn(" — Домашняя работа №1", a.title)

    def test_seq_increments_per_student(self):
        self.client.login(username="t", password="pass")
        self._post()
        self._post()
        a = Assignment.objects.latest("id")
        self.assertEqual(a.student_seq, 2)
        self.assertIn("№2", a.title)
```

- [ ] **Step 2: Run to verify fails**

```bash
python manage.py test core.tests.test_assignment_title_autogen -v 1
```
Expected: FAIL (поля `kind/student_seq` отсутствуют).

- [ ] **Step 3: Commit failing test**

```bash
git add core/tests/test_assignment_title_autogen.py
git commit -m "test: assignment title autogen uses exam format and seq"
```

---

### Task 2: GREEN — добавить поля Assignment.kind/student_seq (migration)

**Files:**
- Modify: `/workspace/core/models.py`
- Create: `/workspace/core/migrations/00xx_assignment_kind_and_seq.py`
- Test: `/workspace/core/tests/test_assignment_title_autogen.py`

- [ ] **Step 1: Add fields to model**

В `Assignment` добавить:

```python
    KIND_CHOICES = [
        ("homework", "Домашняя работа"),
        ("test", "Тест"),
        ("control_test", "Контрольный тест"),
    ]
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, null=True, blank=True)
    student_seq = models.IntegerField(null=True, blank=True)
```

- [ ] **Step 2: Create migration**
Сгенерировать миграцию (ручной файл) добавляющую эти поля.

- [ ] **Step 3: Run tests**

```bash
python manage.py test core.tests.test_assignment_title_autogen -v 1
```
Expected: всё ещё FAIL (логики автогенерации нет).

- [ ] **Step 4: Commit**

```bash
git add core/models.py core/migrations
git commit -m "feat: add assignment kind and student sequence"
```

---

### Task 3: GREEN — tutor_create_assignment: порядок полей + kind + автоген title

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/tutor_create_assignment.html`
- Test: `/workspace/core/tests/test_assignment_title_autogen.py`

- [ ] **Step 1: Update template order + add kind select**
В `tutor_create_assignment.html`:
- перенести блок “Формат экзамена” выше “Кому назначить”
- добавить select `name="kind"` с 3 опциями и дефолтом `homework`

- [ ] **Step 2: Update view**
В `tutor_create_assignment`:
- читать `kind = (request.POST.get("kind") or "homework").strip()`
- если `title` пустой:
  - `student_seq = (Assignment.objects.filter(student=student).exclude(student_seq__isnull=True).aggregate(Max("student_seq"))["student_seq__max"] or 0) + 1`
  - `kind_label` маппинг по kind
  - `student_name = student.get_full_name() or student.username`
  - `title = f"{exam_format.name} {exam_format.year} — {student_name} — {kind_label} №{student_seq}"`
- сохранять `kind` и `student_seq` в `Assignment.objects.create(...)`

- [ ] **Step 3: Run tests**

```bash
python manage.py test core.tests.test_assignment_title_autogen -v 1
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/templates/core/tutor_create_assignment.html
git commit -m "feat: autogenerate assignment title with exam format and seq"
```

---

### Task 4: RED — тест: regenerate_task редиректит с focus_task_id

**Files:**
- Create: `/workspace/core/tests/test_tutor_regenerate_task_focus.py`

- [ ] **Step 1: Write failing test**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User


class TutorRegenerateTaskFocusTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ математика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subj, name="T")
        self.t1 = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        self.t2 = Task.objects.create(topic=topic, task_type=tt, correct_answer="2", difficulty=10, exam_points=1)

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=True, exam_format=ef)
        self.assignment.tasks.add(self.t1)

    def test_redirect_contains_focus_task_id(self):
        self.client.login(username="t", password="pass")
        res = self.client.post(reverse("tutor_regenerate_task", args=[self.assignment.id, self.t1.id]))
        self.assertEqual(res.status_code, 302)
        self.assertIn("focus_task_id=", res["Location"])
        self.assertIn(str(self.t2.id), res["Location"])
```

- [ ] **Step 2: Run to verify fails**

```bash
python manage.py test core.tests.test_tutor_regenerate_task_focus -v 1
```
Expected: FAIL (редирект без параметра).

- [ ] **Step 3: Commit failing test**

```bash
git add core/tests/test_tutor_regenerate_task_focus.py
git commit -m "test: regenerate task redirects with focus id"
```

---

### Task 5: GREEN — preview focus (ids + JS) + regenerate redirect param

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/tutor_preview_assignment.html`
- Test: `/workspace/core/tests/test_tutor_regenerate_task_focus.py`

- [ ] **Step 1: Change redirect in tutor_regenerate_task**
После `assignment.tasks.add(new_task)`:
- `return redirect(f\"{reverse('tutor_preview_assignment', args=[assignment.id])}?focus_task_id={new_task.id}\")`

- [ ] **Step 2: Add ids to task cards**
В preview template: на карточке задачи добавить `id="task-{{ task.id }}"`.

- [ ] **Step 3: Add JS focus**
Добавить JS внизу:
- читать `focus_task_id` из `URLSearchParams`
- найти `#task-<id>` и `scrollIntoView`
- временно добавить класс подсветки
- `history.replaceState` чтобы убрать параметр

- [ ] **Step 4: Run tests**

```bash
python manage.py test core.tests.test_tutor_regenerate_task_focus -v 1
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/templates/core/tutor_preview_assignment.html
git commit -m "feat: keep focus on regenerated task in preview"
```

---

### Task 6: Full regression + push

- [ ] **Step 1: Run full suite**

```bash
python manage.py test core.tests -v 1
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

