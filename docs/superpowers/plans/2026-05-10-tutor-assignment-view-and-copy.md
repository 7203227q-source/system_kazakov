# Tutor Assignment View & Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать репетитору read-only просмотр варианта ученика (условие+решение) и кнопку «Копировать» (текст + 1-е изображение) для переноса на онлайн-доску.

**Architecture:** Новый view + новый шаблон для просмотра варианта. Кнопка копирования реализуется в JS через Clipboard API с fallback на `writeText`. Доступ ограничивается по `assignment.tutor`.

**Tech Stack:** Django (views, urls, templates), Clipboard API, fetch, существующий `/proxy-image/`.

---

## Файлы

**Create:**
- `/workspace/core/templates/core/tutor_assignment_view.html`

**Modify:**
- `/workspace/core/views.py`
- `/workspace/core/urls.py`
- `/workspace/core/templates/core/tutor_dashboard.html`
- `/workspace/core/templates/core/tutor_assignment_summary.html`

---

### Task 1: Новый view «Просмотр варианта»

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/urls.py`

- [ ] **Step 1: Добавить view `tutor_assignment_view`**

В `core/views.py` добавить:

```py
@login_required
def tutor_assignment_view(request, assignment_id):
    if request.user.role not in ['tutor', 'admin']:
        return redirect('login')

    qs = Assignment.objects.select_related('student', 'tutor')
    if request.user.role == 'tutor':
        assignment = get_object_or_404(qs, id=assignment_id, tutor=request.user, is_draft=False)
    else:
        assignment = get_object_or_404(qs, id=assignment_id, is_draft=False)

    theme = getattr(request.user, 'preferred_theme', None) or 'classic'
    tasks = assignment.tasks.select_related('task_type').order_by('task_type__number', 'id')
    return render(request, 'core/tutor_assignment_view.html', {
        'assignment': assignment,
        'student': assignment.student,
        'theme': theme,
        'tasks': tasks,
    })
```

- [ ] **Step 2: Добавить URL**

В `core/urls.py` добавить:

```py
path('tutor/assignment/<int:assignment_id>/view/', views.tutor_assignment_view, name='tutor_assignment_view'),
```

- [ ] **Step 3: Smoke-check**

```bash
python -m compileall -q /workspace/core
```

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/urls.py
git commit -m "feat: add tutor assignment view page"
```

---

### Task 2: Шаблон просмотра + кнопка «Копировать»

**Files:**
- Create: `/workspace/core/templates/core/tutor_assignment_view.html`

- [ ] **Step 1: Разметка списка задач**

Для каждой задачи выводить:
- номер типа + название,
- условие: `{{ task.get_content_for_theme(theme)|safe }}`,
- решение: `{{ task.get_solution_for_theme(theme)|safe }}`.

- [ ] **Step 2: Кнопка «Копировать»**

Добавить кнопку:

```html
<button type="button" class="copy-task-btn" data-task-id="{{ task.id }}">Копировать</button>
```

Контейнер условия:

```html
<div id="task-content-{{ task.id }}">...</div>
```

JS:
- `text = el.innerText.trim()`
- `img = el.querySelector('img')`
- если img есть:
  - `src = img.getAttribute('src')`
  - если `src` начинается с `http` → `src = '/proxy-image/?url=' + encodeURIComponent(src)`
  - `blob = await fetch(src).then(r=>r.blob())`
  - `await navigator.clipboard.write([new ClipboardItem({[blob.type]: blob, 'text/plain': new Blob([text],{type:'text/plain'})})])`
- иначе:
  - `await navigator.clipboard.writeText(text)`

- [ ] **Step 3: Smoke-check**

```bash
python -m compileall -q /workspace/core
```

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/tutor_assignment_view.html
git commit -m "feat: tutor assignment view template with copy button"
```

---

### Task 3: Ссылки «Просмотр» из дашборда и сводки

**Files:**
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`
- Modify: `/workspace/core/templates/core/tutor_assignment_summary.html`

- [ ] **Step 1: Добавить ссылку в список вариантов на `tutor_dashboard`**

В карточке варианта рядом с заголовком добавить:

```django
<a href="{% url 'tutor_assignment_view' a.id %}" class="text-xs text-primary font-bold hover:underline">Просмотр</a>
```

- [ ] **Step 2: Добавить кнопку на `tutor_assignment_summary`**

В верхнем блоке рядом с “Назад” добавить:

```django
<a href="{% url 'tutor_assignment_view' assignment.id %}" class="...">Открыть просмотр</a>
```

- [ ] **Step 3: Smoke-check**

```bash
python -m compileall -q /workspace/core
```

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/tutor_dashboard.html core/templates/core/tutor_assignment_summary.html
git commit -m "feat: add tutor assignment view links"
```

---

### Task 4: Push

- [ ] **Step 1: Push**

```bash
git push origin main
```

