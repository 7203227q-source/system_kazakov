# Points Badges & Assignment Ordering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Показать «Баллы X/Y» в последних решениях/ошибках и зафиксировать порядок задач в вариантах (1..N по типу), чтобы номера не «съезжали».

**Architecture:** Меняем только отображение (templates) и порядок выборки задач (views). Данные остаются в `Submission` (`score/primary_score`) и `Task.exam_points`, порядок задач задаём сортировкой queryset при рендере (`order_by('task_type__number', 'id')`).

**Tech Stack:** Django templates + Django ORM.

---

## Файлы

**Modify:**
- `/workspace/core/templates/core/student_dashboard.html` — добавить блок «Последние решения» и бейдж «Баллы X/Y».
- `/workspace/core/templates/core/tutor_dashboard.html` — добавить бейдж «Баллы X/Y» в блоке `recent_mistakes`.
- `/workspace/core/views.py`:
  - `student_dashboard` — убедиться, что `recent_submissions` содержит `select_related('task', 'task__task_type')`.
  - `tutor_preview_assignment`, `student_solve_assignment`, `student_assignment_summary` — сортировать задачи варианта.

---

### Task 1: Баллы X/Y в последних решениях ученика

**Files:**
- Modify: `/workspace/core/views.py` (`student_dashboard`)
- Modify: `/workspace/core/templates/core/student_dashboard.html`

- [ ] **Step 1: Подготовить queryset `recent_submissions`**

В `student_dashboard` заменить:

```py
recent_submissions = Submission.objects.filter(student=request.user).order_by('-created_at')[:5]
```

на:

```py
recent_submissions = (
    Submission.objects
    .filter(student=request.user)
    .select_related('task', 'task__task_type')
    .order_by('-created_at')[:7]
)
```

- [ ] **Step 2: Добавить блок «Последние решения» в шаблон**

В `student_dashboard.html` в правой колонке добавить карточку со списком `recent_submissions` и бейджем:

```django
Баллы:
{% if sub.task.exam_points|default:1 > 1 %}
  {{ sub.primary_score|default:0 }}/{{ sub.task.exam_points|default:0 }}
{% else %}
  {% if sub.is_correct %}1{% else %}0{% endif %}/{{ sub.task.exam_points|default:1 }}
{% endif %}
```

- [ ] **Step 3: Smoke-check**

Запустить:

```bash
python -m compileall -q /workspace/core
```

Ожидание: exit code 0.

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/templates/core/student_dashboard.html
git commit -m "feat: show points badge in student recent submissions"
```

---

### Task 2: Баллы X/Y в последних ошибках репетитора

**Files:**
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`

- [ ] **Step 1: Добавить бейдж баллов в блок `recent_mistakes`**

Добавить рядом с датой/ID:

```django
Баллы:
{% if mistake.task.exam_points|default:1 > 1 %}
  {{ mistake.primary_score|default:0 }}/{{ mistake.task.exam_points|default:0 }}
{% else %}
  {% if mistake.is_correct %}1{% else %}0{% endif %}/{{ mistake.task.exam_points|default:1 }}
{% endif %}
```

- [ ] **Step 2: Smoke-check**

```bash
python -m compileall -q /workspace/core
```

- [ ] **Step 3: Commit**

```bash
git add core/templates/core/tutor_dashboard.html
git commit -m "feat: show points badge in tutor recent mistakes"
```

---

### Task 3: Стабильный порядок задач в варианте

**Files:**
- Modify: `/workspace/core/views.py`

- [ ] **Step 1: Отсортировать задачи в `tutor_preview_assignment`**

Заменить:

```py
tasks_qs = assignment.tasks.all()
```

на:

```py
tasks_qs = assignment.tasks.select_related('task_type').order_by('task_type__number', 'id')
```

- [ ] **Step 2: Отсортировать задачи в `student_solve_assignment` и `student_assignment_summary`**

Заменить в обоих местах:

```py
tasks = assignment.tasks.all()
```

на:

```py
tasks = assignment.tasks.select_related('task_type').order_by('task_type__number', 'id')
```

- [ ] **Step 3: Smoke-check**

```bash
python -m compileall -q /workspace/core
```

- [ ] **Step 4: Commit**

```bash
git add core/views.py
git commit -m "fix: stable ordering for assignment tasks"
```

---

### Task 4: Push

- [ ] **Step 1: Push**

```bash
git push origin main
```

