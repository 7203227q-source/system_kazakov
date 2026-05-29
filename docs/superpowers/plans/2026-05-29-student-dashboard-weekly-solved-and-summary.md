# Student Dashboard Weekly Solved Chart + Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в дашборд ученика недельную диаграмму решаемости (правильно/неправильно) и сводку по решениям, считая по выбранному предмету (`subject_id`).

**Architecture:** Вынести расчёты недельной диаграммы и сводки в переиспользуемый модуль (`core/dashboard_analytics.py`) и использовать его в `student_dashboard`. Формат данных для диаграммы — совместимый с Chart.js (labels/correct/incorrect), как в `tutor_dashboard`.

**Tech Stack:** Django, ORM, Chart.js (через CDN), Django TestCase (`python manage.py test`).

---

## File Map

- Create: `/workspace/core/dashboard_analytics.py` — функции для расчёта данных графика и сводки.
- Modify: `/workspace/core/views.py` — `student_dashboard`: добавить новые поля в контекст.
- Modify: `/workspace/core/templates/core/student_dashboard.html` — добавить новый `<canvas>` и отрисовку Chart.js + карточки сводки.
- Create: `/workspace/core/tests/test_student_dashboard_weekly_solved_and_summary.py` — регресс-тесты данных в контексте.

---

## Behavior Spec (точные требования)

### Фильтрация “по соответствующим предметам”

- Используется предмет, выбранный на дашборде ученика (`active_subject_id` / GET `subject_id`).
- Если `active_subject_id` отсутствует и у ученика есть профили, используется первый профиль (текущее поведение `student_dashboard`).
- Если предмет не определён (нет профилей и нет `subject_id`), недельная диаграмма и сводка не показываются.

### Недельная диаграмма решаемости

- Период: 7 календарных дней, включая сегодня (D-6..D).
- Для каждой пары (`date`, `task_id`) берём **последнюю попытку** в этот день:
  - если последняя попытка `is_correct=True` → засчитываем “Правильно”
  - иначе → засчитываем “Неправильно”
- Итог по дню:
  - `correct[day]` — число задач, у которых последняя попытка в этот день корректна
  - `incorrect[day]` — число задач, у которых последняя попытка в этот день некорректна (включая `False` и любые иные значения)
- Данные отдаются в JSON:
  - `labels`: список из 7 строковых меток (например, `["Пн", "Вт", ...]` или `["23 мая", ...]`)
  - `correct`: список из 7 int
  - `incorrect`: список из 7 int

### Сводка по решениям

- Считается по тем же `Submission` и тому же фильтру предмета.
- Метрики:
  - `student_total_submissions`: всего попыток (кол-во `Submission` после фильтра)
  - `student_correct_rate`: доля правильных в процентах (0..100, округление до целого), либо `None`, если попыток нет
  - (опционально для UI) `student_correct_submissions` / `student_incorrect_submissions`

---

## Task 1: Add Failing Tests (TDD)

**Files:**
- Create: `/workspace/core/tests/test_student_dashboard_weekly_solved_and_summary.py`

- [ ] **Step 1: Write failing tests**

```python
import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, StudentSubjectProfile, Subject, Submission, Task, TaskType, Topic, User


class StudentDashboardWeeklySolvedAndSummaryTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pw", role="student")
        self.client.force_login(self.student)

        self.subject = Subject.objects.create(name="Физика")
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")
        self.ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ физика", year=2026, is_active=True)
        self.tt = TaskType.objects.create(
            exam_format=self.ef,
            number=1,
            name="№1",
            max_points=1,
            is_extended_answer=False,
        )
        StudentSubjectProfile.objects.create(student=self.student, subject=self.subject, exam_format=self.ef, xp=0)

        self.task = Task.objects.create(topic=self.topic, task_type=self.tt, correct_answer="1", exam_points=1)

    def test_dashboard_provides_weekly_solved_chart_data_for_active_subject(self):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        Submission.objects.create(student=self.student, task=self.task, is_correct=False, created_at=timezone.now() - timedelta(days=1, hours=1))
        Submission.objects.create(student=self.student, task=self.task, is_correct=True, created_at=timezone.now() - timedelta(days=1, minutes=1))

        res = self.client.get(reverse("student_dashboard"), {"subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)

        raw = res.context.get("weekly_solved_chart_data")
        self.assertTrue(raw)
        data = json.loads(raw)

        self.assertEqual(len(data["labels"]), 7)
        self.assertEqual(len(data["correct"]), 7)
        self.assertEqual(len(data["incorrect"]), 7)

        idx = data["labels"].index(yesterday.strftime("%d %b"))
        self.assertEqual(int(data["correct"][idx]), 1)
        self.assertEqual(int(data["incorrect"][idx]), 0)

    def test_dashboard_provides_submission_summary_for_active_subject(self):
        Submission.objects.create(student=self.student, task=self.task, is_correct=False)
        Submission.objects.create(student=self.student, task=self.task, is_correct=True)

        res = self.client.get(reverse("student_dashboard"), {"subject_id": self.subject.id})
        self.assertEqual(res.status_code, 200)

        self.assertEqual(int(res.context["student_total_submissions"]), 2)
        self.assertEqual(int(res.context["student_correct_rate"]), 50)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python manage.py test core.tests.test_student_dashboard_weekly_solved_and_summary -v 2
```

Expected: FAIL (`weekly_solved_chart_data` / `student_total_submissions` отсутствуют).

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_student_dashboard_weekly_solved_and_summary.py
git commit -m "test(student): weekly solved chart and summary on dashboard"
```

---

## Task 2: Implement Dashboard Analytics Helpers

**Files:**
- Create: `/workspace/core/dashboard_analytics.py`
- Test: `/workspace/core/tests/test_student_dashboard_weekly_solved_and_summary.py`

- [ ] **Step 1: Create helpers**

```python
import json
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from core.models import Submission


def build_weekly_solved_chart_data(student, *, subject_id: int | None, today=None) -> str | None:
    if not subject_id:
        return None

    if today is None:
        today = timezone.localdate()

    start = today - timedelta(days=6)
    qs = (
        Submission.objects.filter(
            student=student,
            created_at__date__gte=start,
            created_at__date__lte=today,
            task__topic__subject_id=int(subject_id),
        )
        .order_by("created_at")
        .values_list("created_at__date", "task_id", "is_correct")
    )

    last_by_day_task = {}
    for d, task_id, is_correct in qs:
        last_by_day_task[(d, int(task_id))] = bool(is_correct)

    labels = []
    correct = []
    incorrect = []
    for i in range(7):
        day = start + timedelta(days=i)
        labels.append(day.strftime("%d %b"))
        c = 0
        w = 0
        for (d, _), ok in last_by_day_task.items():
            if d != day:
                continue
            if ok:
                c += 1
            else:
                w += 1
        correct.append(c)
        incorrect.append(w)

    return json.dumps({"labels": labels, "correct": correct, "incorrect": incorrect})


def build_submission_summary(student, *, subject_id: int | None) -> dict:
    if not subject_id:
        return {"total": 0, "correct": 0, "incorrect": 0, "correct_rate": None}

    qs = Submission.objects.filter(student=student, task__topic__subject_id=int(subject_id))
    total = int(qs.count())
    correct = int(qs.filter(is_correct=True).count())
    incorrect = int(total - correct)
    correct_rate = int(round((correct / total) * 100)) if total > 0 else None
    return {"total": total, "correct": correct, "incorrect": incorrect, "correct_rate": correct_rate}
```

- [ ] **Step 2: Run tests**

Run:

```bash
python manage.py test core.tests.test_student_dashboard_weekly_solved_and_summary -v 2
```

Expected: still FAIL until wired into the view.

- [ ] **Step 3: Commit**

```bash
git add core/dashboard_analytics.py
git commit -m "feat(analytics): weekly solved chart and submission summary helpers"
```

---

## Task 3: Wire Analytics Into student_dashboard

**Files:**
- Modify: `/workspace/core/views.py` — `student_dashboard`
- Test: `/workspace/core/tests/test_student_dashboard_weekly_solved_and_summary.py`

- [ ] **Step 1: Import and add context fields**

In `student_dashboard` after `active_subject_id` resolved and before `return render(...)`, add:

```python
from core.dashboard_analytics import build_submission_summary, build_weekly_solved_chart_data

weekly_solved_chart_data = build_weekly_solved_chart_data(
    request.user,
    subject_id=int(active_subject_id) if active_subject_id else None,
)
summary = build_submission_summary(
    request.user,
    subject_id=int(active_subject_id) if active_subject_id else None,
)
student_total_submissions = summary["total"]
student_correct_rate = summary["correct_rate"]
student_correct_submissions = summary["correct"]
student_incorrect_submissions = summary["incorrect"]
```

Then pass these values into the template context.

- [ ] **Step 2: Run tests**

Run:

```bash
python manage.py test core.tests.test_student_dashboard_weekly_solved_and_summary -v 2
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add core/views.py
git commit -m "feat(student): show weekly solved chart and summary on dashboard"
```

---

## Task 4: Render Weekly Chart + Summary in Template

**Files:**
- Modify: `/workspace/core/templates/core/student_dashboard.html`

- [ ] **Step 1: Add UI block**

Add a section near the existing progress chart:
- `<canvas id="weeklySolvedChart"></canvas>`
- summary cards displaying:
  - `student_total_submissions`
  - `student_correct_rate`
  - optional counts `student_correct_submissions` / `student_incorrect_submissions`

- [ ] **Step 2: Add Chart.js init**

Add script similar to tutor dashboard’s weekly chart:

```javascript
document.addEventListener('DOMContentLoaded', function() {
  const weeklyRaw = '{{ weekly_solved_chart_data|default:""|escapejs }}';
  if (!weeklyRaw || weeklyRaw === '""' || weeklyRaw === 'null') return;
  const weekly = JSON.parse(weeklyRaw);
  if (!weekly.labels || weekly.labels.length === 0) return;

  const el = document.getElementById('weeklySolvedChart');
  if (!el) return;

  new Chart(el.getContext('2d'), {
    type: 'bar',
    data: {
      labels: weekly.labels,
      datasets: [
        { label: 'Правильно', data: weekly.correct, backgroundColor: '#2563EB' },
        { label: 'Неправильно', data: weekly.incorrect, backgroundColor: '#EF4444' }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom' } },
      scales: { y: { beginAtZero: true } }
    }
  });
});
```

- [ ] **Step 3: Run tests smoke**

Run:

```bash
python manage.py test core.tests.test_student_dashboard_weekly_solved_and_summary -v 2
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/student_dashboard.html
git commit -m "feat(student): render weekly solved chart and summary UI"
```

---

## Plan Self-Review

- Spec coverage: реализуются ровно два блока (недельная диаграмма и сводка) и строгая фильтрация по выбранному предмету.
- Placeholder scan: нет TODO/TBD, в задачах есть конкретные файлы, команды и код.
- Type consistency: имена `weekly_solved_chart_data`, `student_total_submissions`, `student_correct_rate` совпадают во view, тестах и шаблоне.

