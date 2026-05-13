# Tutor Dashboard Subject Switcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В дашборде тьютора вся аналитика по выбранному ученику (попытки/точность, график, решаемость по номерам, списки вариантов) должна переключаться по предмету через общий переключатель сверху.

**Architecture:** Один параметр `subject_id` в querystring — единственный источник истины для выбранного предмета. В view строим базовый queryset `submissions_subject` (строго по subject) и от него считаем totals/accuracy; график уже по `DailySnapshot(subject=...)`; решаемость по номерам и списки вариантов синхронизируем с выбранным subject.

**Tech Stack:** Django (views, templates), existing models (`Subject`, `StudentSubjectProfile`, `ExamFormat`, `Submission`, `Task`, `Topic`, `Assignment`, `TaskType`), existing tests (`django.test.TestCase`).

---

## Files to Touch

- Modify: [views.py](file:///workspace/core/views.py) (`tutor_dashboard`)
- Modify: [tutor_dashboard.html](file:///workspace/core/templates/core/tutor_dashboard.html) (верхний переключатель + убрать локальный select)
- Create: `/workspace/core/tests/test_tutor_dashboard_subject_switcher.py`

---

### Task 1: RED — тесты предметной статистики

**Files:**
- Create: `/workspace/core/tests/test_tutor_dashboard_subject_switcher.py`

- [ ] **Step 1: Write failing test for totals/accuracy filtered by subject**

```python
import base64
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class TutorDashboardSubjectSwitcherTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor.students.add(self.student)

        self.subj_math = Subject.objects.create(name="Математика")
        self.subj_phys = Subject.objects.create(name="Физика")
        self.ef_math = ExamFormat.objects.create(subject=self.subj_math, name="ЕГЭ", year=2026, is_active=True)
        self.ef_phys = ExamFormat.objects.create(subject=self.subj_phys, name="ЕГЭ", year=2026, is_active=True)
        self.tt_math = TaskType.objects.create(exam_format=self.ef_math, number=1, name="M1", max_points=1, is_extended_answer=False)
        self.tt_phys = TaskType.objects.create(exam_format=self.ef_phys, number=1, name="P1", max_points=1, is_extended_answer=False)
        self.topic_math = Topic.objects.create(subject=self.subj_math, name="TM")
        self.topic_phys = Topic.objects.create(subject=self.subj_phys, name="TP")
        self.task_math = Task.objects.create(topic=self.topic_math, task_type=self.tt_math, correct_answer="1", difficulty=10, exam_points=1)
        self.task_phys = Task.objects.create(topic=self.topic_phys, task_type=self.tt_phys, correct_answer="1", difficulty=10, exam_points=1)
        TaskVariant.objects.create(task=self.task_math, theme="classic", content="<p>Q</p>", solution="")
        TaskVariant.objects.create(task=self.task_phys, theme="classic", content="<p>Q</p>", solution="")

        a_math = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A1", is_draft=False, is_completed=False, exam_format=self.ef_math)
        a_math.tasks.add(self.task_math)
        a_phys = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A2", is_draft=False, is_completed=False, exam_format=self.ef_phys)
        a_phys.tasks.add(self.task_phys)

        Submission.objects.create(student=self.student, task=self.task_math, assignment=a_math, user_answer="1", is_correct=True, score=1)
        Submission.objects.create(student=self.student, task=self.task_phys, assignment=a_phys, user_answer="0", is_correct=False, score=0)

    def test_totals_and_accuracy_switch_with_subject(self):
        self.client.login(username="t", password="pass")

        url_math = f"{reverse('tutor_dashboard')}?student_id={self.student.id}&subject_id={self.subj_math.id}"
        page_math = self.client.get(url_math)
        self.assertEqual(page_math.status_code, 200)
        self.assertContains(page_math, "Попыток:")
        self.assertContains(page_math, ">1<")  # attempts
        self.assertContains(page_math, "100")  # accuracy

        url_phys = f"{reverse('tutor_dashboard')}?student_id={self.student.id}&subject_id={self.subj_phys.id}"
        page_phys = self.client.get(url_phys)
        self.assertEqual(page_phys.status_code, 200)
        self.assertContains(page_phys, "Попыток:")
        self.assertContains(page_phys, ">1<")  # attempts
        self.assertContains(page_phys, "0")  # accuracy
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python manage.py test core.tests.test_tutor_dashboard_subject_switcher -v 1
```

Expected: FAIL, потому что totals/accuracy пока считаются по всем сабмишенам ученика без фильтра subject.

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_tutor_dashboard_subject_switcher.py
git commit -m "test: tutor dashboard subject-specific totals and accuracy"
```

---

### Task 2: GREEN — предметный фильтр в tutor_dashboard (totals/accuracy, решаемость, варианты)

**Files:**
- Modify: [views.py](file:///workspace/core/views.py)
- Test: `/workspace/core/tests/test_tutor_dashboard_subject_switcher.py`

- [ ] **Step 1: Implement `subject_id` normalization and base queryset**

Внутри `tutor_dashboard`, когда определён `active_profile/chart_subject_id`, создать:
```python
submissions_subject = Submission.objects.filter(
    student=selected_student,
    task__topic__subject_id=chart_subject_id,
)
```

- [ ] **Step 2: Change totals/accuracy to use `submissions_subject`**

Заменить текущий aggregate по `Submission.objects.filter(student=selected_student)` на `submissions_subject`.

- [ ] **Step 3: Ensure solve-rate uses subject filter**

Там где строится `submissions_base` для решаемости по номерам:
1) стартовать от `submissions_subject` (а не от `Submission.objects.filter(student=...)`)
2) дополнительно (если есть `active_exam_format`) — фильтровать по `task__task_type__exam_format=active_exam_format` как сейчас.

- [ ] **Step 4: Filter assignments lists by subject (R4)**

Если `chart_subject_id` определён:
```python
assignments = assignments.filter(exam_format__subject_id=chart_subject_id)
```
и добавить `.select_related('exam_format', 'exam_format__subject')` чтобы не было N+1.

- [ ] **Step 5: Run tests**

```bash
python manage.py test core.tests.test_tutor_dashboard_subject_switcher -v 1
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/views.py
git commit -m "feat: tutor dashboard subject-specific stats"
```

---

### Task 3: GREEN — общий переключатель предмета сверху + убрать локальный select

**Files:**
- Modify: [tutor_dashboard.html](file:///workspace/core/templates/core/tutor_dashboard.html)
- (optional) Modify: [views.py](file:///workspace/core/views.py) to pass any extra context needed

- [ ] **Step 1: Add subject switcher UI in header**

В `header` рядом с заголовком добавить pills:
- брать список из `selected_student.subject_profiles`
- активный — `chart_subject_id`
- ссылки вида:
`?student_id={{ selected_student.id }}&subject_id={{ profile.subject.id }}&range={{ chart_range|default:30 }}`

- [ ] **Step 2: Remove/hide local subject select in “Прогноз и Аналитика”**

Удалить `<select name="subject_id"...>` чтобы не было дублирования управления.

- [ ] **Step 3: Run the new test and a smoke set**

```bash
python manage.py test core.tests.test_tutor_dashboard_subject_switcher -v 1
```

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/tutor_dashboard.html
git commit -m "feat: add global subject switcher to tutor dashboard"
```

---

### Task 4: Regression suite + push

- [ ] **Step 1: Run full test suite**

```bash
python manage.py test core.tests -v 1
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

