# SRS From Assignments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Автоматически добавлять неверные задачи из вариантов в интервальное повторение (SRS), добавить блок «Повторить сегодня» на дашборде ученика и кнопку ручного добавления в SRS в тренажёре.

**Architecture:** Используем существующую модель `SpacedRepetition` и SM-2 функции из `core/services.py` (`process_task_submission`, `get_due_tasks_for_student`). Неверные ответы из вариантов триггерят `process_task_submission(..., grade=1)` (и обновляют `next_review_date`). На дашборде показываем счётчик задач с `next_review_date <= today`. В тренажёре добавляем режим `?mode=srs` и endpoint ручного добавления.

**Tech Stack:** Django (views, templates, urls), existing SRS services, Django tests.

---

## File Structure

**Modify:**
- `/workspace/core/views.py`
- `/workspace/core/urls.py`
- `/workspace/core/templates/core/student_dashboard.html`
- `/workspace/core/templates/core/student_practice.html`

**Create:**
- `/workspace/core/tests/test_srs_from_assignments.py`

---

### Task 1: Тесты (автодобавление в SRS + ручное добавление)

**Files:**
- Create: `/workspace/core/tests/test_srs_from_assignments.py`

- [ ] **Step 1: Написать падающий тест на автодобавление SRS при неверной проверке в варианте**

```py
from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from core.models import User, Subject, ExamFormat, TaskType, Topic, Task, TaskVariant, Assignment, SpacedRepetition


class SrsFromAssignmentsTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='srs_student', password='x', role='student')
        self.tutor = User.objects.create_user(username='srs_tutor', password='x', role='tutor')
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name='Математика')
        ef = ExamFormat.objects.create(subject=subj, name='ЕГЭ', year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name='Тест', max_points=1)
        topic = Topic.objects.create(subject=subj, name='T')
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer='42', difficulty=50, exam_points=1)
        TaskVariant.objects.create(task=self.task, theme='classic', content='<p>U</p>', solution='<p>S</p>')

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title='A', is_draft=False)
        self.assignment.tasks.add(self.task)

    def test_wrong_answer_in_assignment_creates_srs_record(self):
        self.client.force_login(self.student)
        url = reverse('student_check_assignment_task', args=[self.assignment.id, self.task.id])
        self.client.post(url, {'answer': '0'})
        self.assertTrue(SpacedRepetition.objects.filter(student=self.student, task=self.task).exists())
```

- [ ] **Step 2: Написать падающий тест на ручное добавление в SRS из тренажёра**

```py
    def test_manual_add_to_srs_endpoint(self):
        self.client.force_login(self.student)
        url = reverse('student_srs_add', args=[self.task.id])
        self.client.post(url)
        self.assertTrue(SpacedRepetition.objects.filter(student=self.student, task=self.task).exists())
```

- [ ] **Step 3: Запустить тесты (ожидаем FAIL)**

Run:
```bash
python manage.py test core.tests.test_srs_from_assignments -v 2
```

- [ ] **Step 4: Commit тестов**

```bash
git add core/tests/test_srs_from_assignments.py
git commit -m "test: srs is created from wrong assignment answers and manual add"
```

---

### Task 2: Автодобавление неверных задач из вариантов в SRS

**Files:**
- Modify: `/workspace/core/views.py`

- [ ] **Step 1: Импортировать SRS сервис**

Вверху `core/views.py` заменить импорт:

```py
from .services import process_task_submission, get_due_tasks_for_student
```

на алиас, чтобы не путаться с логикой “submission”:

```py
from .services import process_task_submission as srs_process_task_submission, get_due_tasks_for_student
```

- [ ] **Step 2: В `student_check_assignment_task` — если неверно, вызвать SRS**

После вычисления `is_correct`:

```py
if not is_correct:
    srs_process_task_submission(request.user, task, 1)
```

- [ ] **Step 3: В `api_verify_with_ai` — если итоговый score==0, вызвать SRS**

После выставления результатов:

```py
if int(submission.score or 0) == 0:
    srs_process_task_submission(request.user, submission.task, 1)
```

- [ ] **Step 4: В `auto_expire_assignment_if_needed` — для задач, закрытых на 0, вызвать SRS**

В конце цикла по задачам (после гарантии submission с 0):

```py
if int(sub.score or 0) == 0:
    srs_process_task_submission(assignment.student, t, 1)
```

- [ ] **Step 5: Проверка**

```bash
python -m compileall -q /workspace/core
python manage.py test core.tests.test_srs_from_assignments -v 2
```

- [ ] **Step 6: Commit**

```bash
git add core/views.py
git commit -m "feat: auto-add wrong assignment tasks to SRS"
```

---

### Task 3: Режим SRS в тренажёре + ручная кнопка «Добавить в интервальное повторение»

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/urls.py`
- Modify: `/workspace/core/templates/core/student_practice.html`

- [ ] **Step 1: Endpoint ручного добавления**

В `core/views.py`:

```py
@login_required
@require_POST
def student_srs_add(request, task_id):
    if request.user.role != 'student':
        return redirect('login')
    task = get_object_or_404(Task, id=task_id)
    rec, _ = SpacedRepetition.objects.get_or_create(student=request.user, task=task)
    rec.next_review_date = timezone.now().date()
    rec.save(update_fields=['next_review_date'])
    messages.success(request, "Добавлено в интервальное повторение.")
    return redirect(request.META.get('HTTP_REFERER', reverse('student_practice')))
```

В `core/urls.py`:

```py
path('student/practice/<int:task_id>/srs-add/', views.student_srs_add, name='student_srs_add'),
```

- [ ] **Step 2: Режим `?mode=srs` в `student_practice`**

В `student_practice`:
- на GET: если `request.GET.get('mode') == 'srs'`:
  - взять `due = get_due_tasks_for_student(request.user).select_related('task').first()`
  - `task = due.task if due else None`
- на POST: если это режим `mode=srs` (передавать hidden input `mode`):
  - после проверки вызвать `srs_process_task_submission(request.user, task, 5 if is_correct else 1)`

- [ ] **Step 3: Кнопка в шаблоне тренажёра**

В `student_practice.html` добавить форму:

```html
{% if task %}
<form method="POST" action="{% url 'student_srs_add' task.id %}">
  {% csrf_token %}
  <button class="text-xs font-bold bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 px-3 py-2 rounded-lg">
    Добавить в интервальное повторение
  </button>
</form>
{% endif %}
```

И добавить скрытое поле `mode` в форму ответа:

```html
<input type="hidden" name="mode" value="{{ mode|default:'' }}">
```

- [ ] **Step 4: Проверка**

```bash
python -m compileall -q /workspace/core
python manage.py test core.tests.test_srs_from_assignments -v 2
```

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/urls.py core/templates/core/student_practice.html
git commit -m "feat: SRS mode in practice and manual add button"
```

---

### Task 4: Блок «Повторить сегодня» на дашборде ученика

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/student_dashboard.html`

- [ ] **Step 1: Посчитать `due_srs_count`**

В `student_dashboard`:

```py
from .models import SpacedRepetition
due_srs_count = SpacedRepetition.objects.filter(student=request.user, next_review_date__lte=timezone.now().date()).count()
```

Добавить в контекст.

- [ ] **Step 2: Добавить блок в шаблон**

В `student_dashboard.html` под вариантами/тренажёром добавить:
- заголовок «Повторить сегодня»
- счётчик `{{ due_srs_count }}`
- ссылка на `{% url 'student_practice' %}?mode=srs`

- [ ] **Step 3: Проверка**

```bash
python -m compileall -q /workspace/core
python manage.py test core.tests.test_srs_from_assignments -v 2
```

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/templates/core/student_dashboard.html
git commit -m "ui: add 'repeat today' SRS block on student dashboard"
```

---

### Task 5: Финальная проверка и push

- [ ] **Step 1: Полный прогон основных тестов (если не долго)**

```bash
pytest -q || python manage.py test -v 1
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

