# Tutor Dashboard Weekly Solved Chart & Subject Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить на дашборд репетитора (правая панель выбранного ученика) предметную фильтрацию вариантов + недельный график «правильно/неправильно».

**Architecture:** Сервер (`core/views.py:tutor_dashboard`) считает предметные выборки (варианты + недельная агрегация `Submission` за 7 дней) и передаёт в шаблон JSON. Фронт (`core/templates/core/tutor_dashboard.html`) рисует новый bar-chart через Chart.js рядом с уже существующим line-chart.

**Tech Stack:** Django (views/templates/tests), Chart.js (CDN), TailwindCSS.

---

## Файлы и ответственность

**Modify:**
- `core/views.py` — в `tutor_dashboard`:
  - фильтрация `Assignment` по выбранному предмету (`subject_id`) для правой панели;
  - расчёт `weekly_solved_chart_data` (7 дней, correct/incorrect, по последней попытке задачи в день).
- `core/templates/core/tutor_dashboard.html` — добавить UI и JS для нового графика.

**Test (modify/add):**
- `core/tests/test_tutor_dashboard_shows_all_assignments_across_subjects.py` → изменить ожидания под новое поведение (теперь **должны скрываться** варианты других предметов в правой панели).
- `core/tests/test_tutor_dashboard_weekly_solved_chart.py` (новый) — регресс на недельную агрегацию.

---

### Task 1: Обновить регресс-тесты под новое требование (варианты фильтруются по предмету)

**Files:**
- Modify: `core/tests/test_tutor_dashboard_shows_all_assignments_across_subjects.py`

- [ ] **Step 1: Изменить тест так, чтобы он падал на текущем поведении**

Заменить тест на следующий (сохраняем существующий setup, меняем assertion’ы):

```python
class TutorDashboardAssignmentSubjectFilterTests(TestCase):
    def test_tutor_dashboard_hides_assignments_of_other_subjects_in_right_panel(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subj1 = Subject.objects.create(name="Математика")
        subj2 = Subject.objects.create(name="Физика")
        StudentSubjectProfile.objects.create(student=student, subject=subj1, xp=0, level=1, target_score=80)
        StudentSubjectProfile.objects.create(student=student, subject=subj2, xp=0, level=1, target_score=80)

        ef1 = ExamFormat.objects.create(subject=subj1, name="ЕГЭ", year=2026, is_active=True)
        ef2 = ExamFormat.objects.create(subject=subj2, name="ЕГЭ физика", year=2026, is_active=True)

        topic1 = Topic.objects.create(subject=subj1, name="T1")
        topic2 = Topic.objects.create(subject=subj2, name="T2")
        tt1 = TaskType.objects.create(exam_format=ef1, number=1, name="1", max_points=1)
        tt2 = TaskType.objects.create(exam_format=ef2, number=1, name="1", max_points=1)
        task1 = Task.objects.create(topic=topic1, task_type=tt1, correct_answer="1", difficulty=10, exam_points=1)
        task2 = Task.objects.create(topic=topic2, task_type=tt2, correct_answer="1", difficulty=10, exam_points=1)

        a1 = Assignment.objects.create(tutor=tutor, student=student, title="Матем вариант", is_draft=False, exam_format=ef1)
        a2 = Assignment.objects.create(tutor=tutor, student=student, title="Физика вариант", is_draft=False, exam_format=ef2)
        a1.tasks.add(task1)
        a2.tasks.add(task2)

        self.client.login(username="t", password="pass")

        url_math = reverse("tutor_dashboard") + f"?student_id={student.id}&subject_id={subj1.id}"
        r_math = self.client.get(url_math)
        self.assertEqual(r_math.status_code, 200)
        html_math = r_math.content.decode("utf-8")
        self.assertIn("Матем вариант", html_math)
        self.assertNotIn("Физика вариант", html_math)

        url_phys = reverse("tutor_dashboard") + f"?student_id={student.id}&subject_id={subj2.id}"
        r_phys = self.client.get(url_phys)
        self.assertEqual(r_phys.status_code, 200)
        html_phys = r_phys.content.decode("utf-8")
        self.assertIn("Физика вариант", html_phys)
        self.assertNotIn("Матем вариант", html_phys)
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run:
```bash
pytest core/tests/test_tutor_dashboard_shows_all_assignments_across_subjects.py -q
```

Expected: FAIL (потому что сейчас варианты не фильтруются и оба присутствуют).

- [ ] **Step 3: Commit (только тесты)**

```bash
git add core/tests/test_tutor_dashboard_shows_all_assignments_across_subjects.py
git commit -m "test: tutor dashboard filters assignments by selected subject"
```

---

### Task 2: Реализовать предметную фильтрацию вариантов в `tutor_dashboard`

**Files:**
- Modify: `core/views.py` (функция `tutor_dashboard`)

- [ ] **Step 1: Внести минимальную правку в queryset `assignments`**

В `tutor_dashboard` после формирования `assignments = (Assignment.objects.filter(...))` добавить фильтр по `chart_subject_id` (который уже является “активным предметом” правой панели):

```python
from django.db.models import Q

assignments = (
    Assignment.objects
    .filter(tutor=request.user, student=selected_student, is_draft=False, is_deleted=False)
    .select_related('exam_format', 'exam_format__subject')
    .prefetch_related('tasks', 'tasks__task_type')
    .order_by('-created_at')
)

if chart_subject_id:
    assignments = assignments.filter(
        Q(exam_format__subject_id=chart_subject_id)
        | Q(exam_format__isnull=True, tasks__topic__subject_id=chart_subject_id)
    ).distinct()
```

Примечание: `distinct()` нужен из-за join по `tasks__...`.

- [ ] **Step 2: Прогнать обновлённый тест**

Run:
```bash
pytest core/tests/test_tutor_dashboard_shows_all_assignments_across_subjects.py -q
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add core/views.py
git commit -m "fix: filter tutor dashboard assignments by selected subject"
```

---

### Task 3: Добавить расчёт `weekly_solved_chart_data` (7 дней, уникальные задачи/день)

**Files:**
- Create: `core/tests/test_tutor_dashboard_weekly_solved_chart.py`
- Modify: `core/views.py` (функция `tutor_dashboard`)

- [ ] **Step 1: Написать падающий тест на недельную агрегацию**

Создать файл `core/tests/test_tutor_dashboard_weekly_solved_chart.py`:

```python
import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, StudentSubjectProfile, Subject, Submission, Task, TaskType, Topic, User


class TutorDashboardWeeklySolvedChartTests(TestCase):
    def test_weekly_chart_counts_unique_tasks_per_day_by_last_attempt(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        StudentSubjectProfile.objects.create(student=student, subject=subj, exam_format=ef)

        topic = Topic.objects.create(subject=subj, name="T")
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1)
        task_a = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        task_b = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)

        today = timezone.localdate()
        d1 = today - timezone.timedelta(days=1)
        d2 = today - timezone.timedelta(days=2)

        # День d2: task_a сначала неверно, потом верно => итог дня: correct=1 incorrect=0
        s1 = Submission.objects.create(student=student, task=task_a, user_answer="0", is_correct=False, score=0)
        Submission.objects.filter(id=s1.id).update(created_at=timezone.make_aware(timezone.datetime.combine(d2, timezone.datetime.min.time())))
        s2 = Submission.objects.create(student=student, task=task_a, user_answer="1", is_correct=True, score=1)
        Submission.objects.filter(id=s2.id).update(created_at=timezone.make_aware(timezone.datetime.combine(d2, timezone.datetime.max.time().replace(microsecond=0))))

        # День d1: task_b неверно => correct=0 incorrect=1
        s3 = Submission.objects.create(student=student, task=task_b, user_answer="0", is_correct=False, score=0)
        Submission.objects.filter(id=s3.id).update(created_at=timezone.make_aware(timezone.datetime.combine(d1, timezone.datetime.max.time().replace(microsecond=0))))

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"), {"student_id": student.id, "subject_id": subj.id})
        self.assertEqual(res.status_code, 200)

        raw = res.context.get("weekly_solved_chart_data")
        self.assertTrue(raw)
        data = json.loads(raw)

        # Находим индексы нужных дат по меткам (формат меток будет d.m + день недели; проверяем по окончанию)
        labels = data["labels"]
        idx_d2 = next(i for i, x in enumerate(labels) if x.endswith(d2.strftime("%d.%m")))
        idx_d1 = next(i for i, x in enumerate(labels) if x.endswith(d1.strftime("%d.%m")))

        self.assertEqual(data["correct"][idx_d2], 1)
        self.assertEqual(data["incorrect"][idx_d2], 0)
        self.assertEqual(data["correct"][idx_d1], 0)
        self.assertEqual(data["incorrect"][idx_d1], 1)
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает (контекста ещё нет)**

Run:
```bash
pytest core/tests/test_tutor_dashboard_weekly_solved_chart.py -q
```
Expected: FAIL (`weekly_solved_chart_data` отсутствует/None).

- [ ] **Step 3: Реализовать расчёт в `tutor_dashboard`**

В `core/views.py` внутри блока `if selected_student:` после вычисления `chart_subject_id` (и до `context = {...}`) добавить:

```python
from datetime import timedelta

weekly_solved_chart_data = None
if chart_subject_id:
    start_week = today - timedelta(days=6)
    day_list = [start_week + timedelta(days=i) for i in range(7)]

    # Русские короткие дни недели (weekday(): 0=Mon)
    wd = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    labels = [f"{wd[d.weekday()]} {d.strftime('%d.%m')}" for d in day_list]

    # Берём все сабмишены за неделю и считаем уникальные задачи в день по последней попытке
    qs = (
        Submission.objects.filter(
            student=selected_student,
            created_at__date__gte=start_week,
            created_at__date__lte=today,
            is_correct__isnull=False,
        )
        .filter(task__topic__subject_id=chart_subject_id)
        .order_by("created_at")
        .values_list("created_at", "task_id", "is_correct")
    )

    last_by_day_task: dict[tuple, bool] = {}
    for created_at, task_id, is_correct in qs:
        d = created_at.date()
        last_by_day_task[(d, int(task_id))] = bool(is_correct)

    correct = []
    incorrect = []
    for d in day_list:
        c = 0
        ic = 0
        for (dd, _tid), v in last_by_day_task.items():
            if dd != d:
                continue
            if v:
                c += 1
            else:
                ic += 1
        correct.append(c)
        incorrect.append(ic)

    weekly_solved_chart_data = json.dumps(
        {"labels": labels, "correct": correct, "incorrect": incorrect},
        ensure_ascii=False,
    )
```

Оптимизация (если понадобится позже): заменить внутренний цикл на предварительную агрегацию `by_day = {date: {...}}`, но на 7 дней это не критично.

- [ ] **Step 4: Прогнать тест**

Run:
```bash
pytest core/tests/test_tutor_dashboard_weekly_solved_chart.py -q
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/tests/test_tutor_dashboard_weekly_solved_chart.py
git commit -m "feat: add weekly correct/incorrect chart data to tutor dashboard"
```

---

### Task 4: Добавить новый график в `tutor_dashboard.html` и отрисовку через Chart.js

**Files:**
- Modify: `core/templates/core/tutor_dashboard.html`

- [ ] **Step 1: Добавить блок canvas под существующим графиком**

В блоке «Прогноз и Аналитика» сразу после секции с `<canvas id="studentProgressChart">` добавить:

```html
<div class="mt-6 bg-gray-50 rounded-xl border border-gray-100 p-4">
  <div class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">
    За последнюю неделю: правильно / неправильно
  </div>
  {% if weekly_solved_chart_data %}
    <div class="relative h-56 w-full">
      <canvas id="studentWeeklySolvedChart"></canvas>
    </div>
  {% else %}
    <div class="text-sm text-gray-500">Нет данных за последнюю неделю.</div>
  {% endif %}
</div>
```

- [ ] **Step 2: Добавить JS инициализацию bar-chart**

Внизу в `<script>` рядом с текущим блоком line-chart добавить:

```js
const weeklyRaw = '{{ weekly_solved_chart_data|default:""|escapejs }}';
if (weeklyRaw) {
  try {
    const weekly = JSON.parse(weeklyRaw);
    const wctx = document.getElementById('studentWeeklySolvedChart');
    if (wctx && weekly && Array.isArray(weekly.labels)) {
      new Chart(wctx, {
        type: 'bar',
        data: {
          labels: weekly.labels,
          datasets: [
            { label: 'Правильно', data: weekly.correct, backgroundColor: '#2563EB' },
            { label: 'Неправильно', data: weekly.incorrect, backgroundColor: '#EF4444' },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
          plugins: { legend: { display: true, position: 'bottom' } },
        },
      });
    }
  } catch (e) {}
}
```

- [ ] **Step 3: Добавить простой smoke-тест на наличие canvas в HTML**

В `core/tests/test_tutor_dashboard_weekly_solved_chart.py` добавить ещё одну проверку:

```python
self.assertContains(res, 'id="studentWeeklySolvedChart"')
```

Run:
```bash
pytest core/tests/test_tutor_dashboard_weekly_solved_chart.py -q
```

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/tutor_dashboard.html core/tests/test_tutor_dashboard_weekly_solved_chart.py
git commit -m "feat: render weekly correct/incorrect chart on tutor dashboard"
```

---

### Task 5: Прогон всего набора тестов и финальный коммит/пуш

**Files:** (как затронуто выше)

- [ ] **Step 1: Прогнать полный тест-сьют**

Run:
```bash
pytest -q
```
Expected: PASS

- [ ] **Step 2: Быстрая проверка, что фильтр не ломает переключатель предметов**

Run:
```bash
pytest core/tests/test_tutor_dashboard_subject_switcher.py -q
```
Expected: PASS

- [ ] **Step 3: Push**

```bash
git push
```

---

## Self-review (перед стартом выполнения)

Покрытие спеки задачами:
- фильтрация вариантов по предмету (правая панель) → Task 1-2 ✅
- недельный график correct/incorrect по дням, по всем решениям, по последней попытке → Task 3-4 ✅
- предметность (математика/физика) → используется `subject_id`/`chart_subject_id` в обеих частях ✅

Placeholder scan:
- нет TODO/TBD, все шаги содержат конкретные команды/код ✅

---

## Execution choice

План сохранён в `docs/superpowers/plans/2026-05-14-tutor-dashboard-weekly-solved-chart-and-subject-filter.md`.

Два варианта выполнения:
1) **Subagent-Driven (recommended)** — я запускаю отдельного subagent’а на каждую Task и делаю ревью между шагами
2) **Inline Execution** — выполняю шаги в этой сессии через executing-plans

Какой вариант выбираете?

