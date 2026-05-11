# Subject Streak (per StudentSubjectProfile) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать рабочий стрик “дней занятий” **по предметам**: при любой попытке решения задачи по предмету стрик продлевается 1 раз в день, и отображается на дашборде ученика для активного предмета.

**Architecture:** Добавляем `last_streak_date` в `StudentSubjectProfile` и функцию `touch_subject_streak(student, subject, today)`; вызываем её из `record_task_log()` и из `student_check_assignment_task()` (чтобы не требовать “Завершить вариант”). В UI дашборда показываем `active_profile.current_streak`.

**Tech Stack:** Django ORM, существующие `core/analytics.py`, `core/views.py`, шаблоны.

---

## File Map

**Modify**
- `core/models.py` (поле last_streak_date)
- `core/migrations/0036_studentsubjectprofile_last_streak_date.py` (миграция)
- `core/analytics.py` (touch_subject_streak + вызов из record_task_log)
- `core/views.py` (вызов touch_subject_streak из student_check_assignment_task)
- `core/templates/core/student_dashboard.html` (показ предметного стрика)

**Create**
- `core/tests/test_subject_streak.py` (unit/integration тесты)

---

### Task 1: Tests for streak rules (RED)

**Files:**
- Create: `core/tests/test_subject_streak.py`

- [ ] **Step 1: Write failing unit tests for touch_subject_streak**

```python
import datetime
from django.test import TestCase
from django.utils import timezone

from core.analytics import touch_subject_streak
from core.models import Subject, User, StudentSubjectProfile


class SubjectStreakTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.subject = Subject.objects.create(name="Математика")
        self.profile = StudentSubjectProfile.objects.create(student=self.student, subject=self.subject, target_score=80, current_streak=0)

    def test_first_touch_sets_streak_to_1(self):
        today = datetime.date(2026, 5, 11)
        touch_subject_streak(self.student, self.subject, today=today)
        self.profile.refresh_from_db()
        assert self.profile.current_streak == 1
        assert self.profile.last_streak_date == today

    def test_second_day_increments(self):
        d1 = datetime.date(2026, 5, 11)
        d2 = datetime.date(2026, 5, 12)
        touch_subject_streak(self.student, self.subject, today=d1)
        touch_subject_streak(self.student, self.subject, today=d2)
        self.profile.refresh_from_db()
        assert self.profile.current_streak == 2
        assert self.profile.last_streak_date == d2

    def test_same_day_is_idempotent(self):
        d1 = datetime.date(2026, 5, 11)
        touch_subject_streak(self.student, self.subject, today=d1)
        touch_subject_streak(self.student, self.subject, today=d1)
        self.profile.refresh_from_db()
        assert self.profile.current_streak == 1

    def test_gap_resets_to_1(self):
        d1 = datetime.date(2026, 5, 11)
        d3 = datetime.date(2026, 5, 13)
        touch_subject_streak(self.student, self.subject, today=d1)
        touch_subject_streak(self.student, self.subject, today=d3)
        self.profile.refresh_from_db()
        assert self.profile.current_streak == 1
        assert self.profile.last_streak_date == d3
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
python manage.py test core.tests.test_subject_streak -v 1
```

Expected: FAIL (нет функции/поля).

---

### Task 2: Add last_streak_date to StudentSubjectProfile (GREEN)

**Files:**
- Modify: `core/models.py`
- Create: `core/migrations/0036_studentsubjectprofile_last_streak_date.py`

- [ ] **Step 1: Add field**

```python
last_streak_date = models.DateField(null=True, blank=True, verbose_name="Дата последнего дня стрика")
```

- [ ] **Step 2: Create migration**

Run:
```bash
python manage.py makemigrations core
```

- [ ] **Step 3: Run tests (still failing)**

Run:
```bash
python manage.py test core.tests.test_subject_streak -v 1
```

Expected: still FAIL (нет функции).

---

### Task 3: Implement touch_subject_streak + hook it into analytics (GREEN)

**Files:**
- Modify: `core/analytics.py`
- Test: `core/tests/test_subject_streak.py`

- [ ] **Step 1: Implement function**

Add to `core/analytics.py`:

```python
def touch_subject_streak(student, subject, *, today=None):
    from django.utils import timezone
    today = today or timezone.now().date()
    profile, _ = StudentSubjectProfile.objects.get_or_create(student=student, subject=subject)
    last = profile.last_streak_date

    if last == today:
        return profile
    if last == (today - datetime.timedelta(days=1)):
        profile.current_streak = int(profile.current_streak or 0) + 1
    else:
        profile.current_streak = 1
    profile.last_streak_date = today
    profile.save(update_fields=["current_streak", "last_streak_date"])

    # keep global streak field meaningful for legacy UI (max across subjects)
    try:
        mx = StudentSubjectProfile.objects.filter(student=student).aggregate(m=Max("current_streak")).get("m") or 0
        if int(student.current_streak or 0) != int(mx):
            student.current_streak = int(mx)
            student.save(update_fields=["current_streak"])
    except Exception:
        pass
    return profile
```

- [ ] **Step 2: Call it from record_task_log**

In `record_task_log(...)`, after `TaskLog.objects.create(...)`:
```python
touch_subject_streak(student, task.topic.subject)
```

- [ ] **Step 3: Run tests**

Run:
```bash
python manage.py test core.tests.test_subject_streak -v 1
```

Expected: PASS.

---

### Task 4: Ensure streak counts attempts inside assignments (GREEN)

**Files:**
- Modify: `core/views.py`
- Test: `core/tests/test_subject_streak.py`

- [ ] **Step 1: Add integration test for student_check_assignment_task**

Add to `core/tests/test_subject_streak.py`:
```python
from django.urls import reverse
from core.models import ExamFormat, Topic, TaskType, Task, TaskVariant, Assignment

def test_assignment_check_touches_streak(self):
    tutor = User.objects.create_user(username="t", password="pass", role="tutor")
    tutor.students.add(self.student)
    ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ математика", year=2026, is_active=True)
    topic = Topic.objects.create(subject=self.subject, name="Задания")
    tt = TaskType.objects.create(exam_format=ef, number=1, name="Тип 1", max_points=1)
    task = Task.objects.create(topic=topic, task_type=tt, subtype_tag="x", correct_answer="1", difficulty=50, exam_points=1)
    TaskVariant.objects.create(task=task, theme="classic", content="x", solution="y")
    a = Assignment.objects.create(tutor=tutor, student=self.student, title="A", is_draft=False)
    a.tasks.add(task)

    self.client.login(username="s", password="pass")
    res = self.client.post(reverse("student_check_assignment_task", args=[a.id, task.id]), {"answer": "0"})
    assert res.status_code == 200
    self.profile.refresh_from_db()
    assert self.profile.current_streak == 1
```

- [ ] **Step 2: Implement hook in view**

In `student_check_assignment_task`, after getting `task`:
```python
from core.analytics import touch_subject_streak
touch_subject_streak(request.user, task.topic.subject)
```

- [ ] **Step 3: Run tests**

Run:
```bash
python manage.py test core.tests.test_subject_streak -v 1
```

Expected: PASS.

---

### Task 5: Update student dashboard UI to show subject streak (REFACTOR)

**Files:**
- Modify: `core/templates/core/student_dashboard.html`

- [ ] Replace:
```django
{{ user.current_streak }} дней в ударе
```
with:
```django
{{ active_profile.current_streak|default:0 }} дней в ударе
```

---

### Task 6: Run full suite + commit + push

- [ ] Run:
```bash
python manage.py test core.tests -v 1
```

- [ ] Commit and push:
```bash
git add core/models.py core/migrations core/analytics.py core/views.py core/templates/core/student_dashboard.html core/tests/test_subject_streak.py docs/superpowers/specs/2026-05-11-subject-streak-design.md docs/superpowers/plans/2026-05-11-subject-streak.md
git commit -m "feat: add per-subject streak tracking"
git push origin main_sync:main
```

