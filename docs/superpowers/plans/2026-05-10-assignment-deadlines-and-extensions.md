# Assignment Deadlines & Extensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить дедлайны на варианты (Assignment) с авто-закрытием по сроку (0 за нерешённые) и запросами продления “+N дней” от ученика с подтверждением репетитора и переоткрытием варианта.

**Architecture:** Дедлайн хранится как `Assignment.due_date` (дата до конца дня). При заходе на страницы ученика/репетитора выполняется проверка просрочки; если срок истёк — вариант закрывается и создаются нулевые `Submission` по нерешённым задачам, плюс пишется `record_task_log` (time_spent=0), чтобы “0” влиял на аналитику. Продление оформляется как `AssignmentExtensionRequest`; при approve вариант переоткрывается и `due_date` сдвигается вперёд.

**Tech Stack:** Django ORM + migrations, Django templates, Django session/messages, существующие `Submission`, `Assignment`, `record_task_log`.

---

## File Structure

**Create:**
- `/workspace/core/migrations/0026_assignment_deadlines_and_extensions.py`
- `/workspace/core/tests/test_assignment_deadlines.py`

**Modify:**
- `/workspace/core/models.py`
- `/workspace/core/views.py`
- `/workspace/core/urls.py`
- `/workspace/core/templates/core/tutor_preview_assignment.html`
- `/workspace/core/templates/core/student_solve_assignment.html`
- `/workspace/core/templates/core/tutor_assignment_view.html`
- `/workspace/core/templates/core/student_dashboard.html`

---

### Task 1: Модели и миграция (due_date + extension requests)

**Files:**
- Modify: `/workspace/core/models.py`
- Create: `/workspace/core/migrations/0026_assignment_deadlines_and_extensions.py`

- [ ] **Step 1: Изменить Assignment**

В `core/models.py` в модели `Assignment` добавить поля:

```py
due_date = models.DateField(null=True, blank=True, verbose_name="Срок (до конца дня)")
is_expired = models.BooleanField(default=False, verbose_name="Просрочено (автозакрыто)")
expired_at = models.DateTimeField(null=True, blank=True, verbose_name="Когда просрочено")
```

- [ ] **Step 2: Добавить AssignmentExtensionRequest**

В `core/models.py` добавить модель:

```py
class AssignmentExtensionRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('approved', 'Одобрено'),
        ('rejected', 'Отклонено'),
    ]

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='extension_requests')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='extension_requests_as_student')
    tutor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='extension_requests_as_tutor')
    requested_days = models.PositiveIntegerField()
    comment = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
```

- [ ] **Step 3: Создать миграцию**

Создать `/workspace/core/migrations/0026_assignment_deadlines_and_extensions.py`:
- `AddField` для трёх полей `Assignment`
- `CreateModel` для `AssignmentExtensionRequest`

- [ ] **Step 4: Smoke-check**

```bash
python -m compileall -q /workspace/core
python manage.py makemigrations --check --dry-run
```

- [ ] **Step 5: Commit**

```bash
git add core/models.py core/migrations/0026_assignment_deadlines_and_extensions.py
git commit -m "feat: assignment deadlines and extension requests models"
```

---

### Task 2: Автозакрытие просроченных вариантов (0 за нерешённые)

**Files:**
- Modify: `/workspace/core/views.py`

- [ ] **Step 1: Добавить helper `auto_expire_assignment_if_needed`**

В `core/views.py` добавить:

```py
from django.utils import timezone

def auto_expire_assignment_if_needed(assignment: Assignment):
    if assignment.is_completed:
        return False
    if not assignment.due_date:
        return False
    today = timezone.now().date()
    if assignment.due_date >= today:
        return False

    assignment.is_completed = True
    assignment.is_expired = True
    assignment.expired_at = timezone.now()
    assignment.save(update_fields=['is_completed', 'is_expired', 'expired_at'])

    tasks = assignment.tasks.all()
    for t in tasks:
        sub, created = Submission.objects.get_or_create(
            student=assignment.student,
            task=t,
            assignment=assignment,
            defaults={'user_answer': '', 'is_correct': False, 'score': 0, 'primary_score': 0},
        )
        if not created:
            if t.exam_points == 1:
                sub.score = 1 if sub.is_correct else 0
            else:
                sub.primary_score = int(sub.primary_score or 0)
                sub.score = int(sub.primary_score or 0)
            sub.save(update_fields=['score', 'primary_score'])

        record_task_log(assignment.student, t, sub, assignment, 0)

    return True
```

- [ ] **Step 2: Вызвать helper в ключевых местах**

Добавить вызовы:
- `student_dashboard`: перед выборкой `pending_assignments` пройтись по `Assignment.objects.filter(student=request.user, is_draft=False, is_completed=False, due_date__isnull=False)`
- `student_solve_assignment`: сразу после загрузки `assignment` вызвать `auto_expire_assignment_if_needed(assignment)` и если `assignment.is_completed` → редирект в summary
- `tutor_dashboard`: при формировании `active_assignments`/списков вариантов вызвать `auto_expire_assignment_if_needed(a)` для вариантов выбранного ученика
- `tutor_assignment_view`: при открытии варианта репетитором тоже вызвать `auto_expire_assignment_if_needed(assignment)`

- [ ] **Step 3: Smoke-check**

```bash
python -m compileall -q /workspace/core
```

- [ ] **Step 4: Commit**

```bash
git add core/views.py
git commit -m "feat: auto-expire overdue assignments with zero scores"
```

---

### Task 3: Репетитор задаёт дедлайн при публикации

**Files:**
- Modify: `/workspace/core/templates/core/tutor_preview_assignment.html`
- Modify: `/workspace/core/views.py`

- [ ] **Step 1: Добавить поле даты в publish form**

В `tutor_preview_assignment.html` в форме publish добавить:

```html
<input type="date" name="due_date" class="bg-white border border-gray-200 px-4 py-2 rounded-lg text-sm" />
```

(Расположить рядом с checkbox Verified.)

- [ ] **Step 2: Принять due_date в tutor_publish_assignment**

В `tutor_publish_assignment`:
- если пришёл `due_date` — распарсить в `datetime.date` (через `fromisoformat`) и сохранить в `assignment.due_date`.

- [ ] **Step 3: Commit**

```bash
git add core/templates/core/tutor_preview_assignment.html core/views.py
git commit -m "feat: allow tutor to set assignment due date on publish"
```

---

### Task 4: Запрос продления от ученика (+N дней)

**Files:**
- Modify: `/workspace/core/urls.py`
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/student_solve_assignment.html`

- [ ] **Step 1: URL**

В `core/urls.py` добавить:

```py
path('student/assignment/<int:assignment_id>/extension-request/', views.student_extension_request, name='student_extension_request'),
```

- [ ] **Step 2: View student_extension_request**

В `core/views.py`:

```py
@login_required
@require_POST
def student_extension_request(request, assignment_id):
    if request.user.role != 'student':
        return redirect('login')
    assignment = get_object_or_404(Assignment, id=assignment_id, student=request.user, is_draft=False)
    days_raw = (request.POST.get('days') or '').strip()
    comment = (request.POST.get('comment') or '').strip()
    if not days_raw.isdigit() or int(days_raw) <= 0 or int(days_raw) > 30:
        messages.error(request, "Введите число дней (1–30).")
        return redirect('student_solve_assignment', assignment_id=assignment.id)

    req, _ = AssignmentExtensionRequest.objects.update_or_create(
        assignment=assignment,
        status='pending',
        defaults={
            'student': assignment.student,
            'tutor': assignment.tutor,
            'requested_days': int(days_raw),
            'comment': comment,
        },
    )
    messages.success(request, "Запрос на продление отправлен репетитору.")
    return redirect('student_solve_assignment', assignment_id=assignment.id)
```

- [ ] **Step 3: UI на странице решения**

В `student_solve_assignment.html` добавить кнопку “Попросить продление” (POST на `student_extension_request`), с простым вводом “+N дней”:
- минимально: поле number + submit
- или JS prompt (если хочется без верстки формы)

- [ ] **Step 4: Commit**

```bash
git add core/urls.py core/views.py core/templates/core/student_solve_assignment.html
git commit -m "feat: student can request assignment deadline extension"
```

---

### Task 5: Одобрение/отклонение продления репетитором + переоткрытие

**Files:**
- Modify: `/workspace/core/urls.py`
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/tutor_assignment_view.html`

- [ ] **Step 1: URL’ы**

В `core/urls.py` добавить:

```py
path('tutor/assignment/<int:assignment_id>/extension-request/<int:req_id>/approve/', views.tutor_extension_approve, name='tutor_extension_approve'),
path('tutor/assignment/<int:assignment_id>/extension-request/<int:req_id>/reject/', views.tutor_extension_reject, name='tutor_extension_reject'),
```

- [ ] **Step 2: Views approve/reject**

В `core/views.py`:

```py
@login_required
@require_POST
def tutor_extension_approve(request, assignment_id, req_id):
    if request.user.role != 'tutor':
        return redirect('login')
    assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user, is_draft=False)
    req = get_object_or_404(AssignmentExtensionRequest, id=req_id, assignment=assignment, status='pending')
    base = assignment.due_date or timezone.now().date()
    if base < timezone.now().date():
        base = timezone.now().date()
    assignment.due_date = base + timezone.timedelta(days=int(req.requested_days))
    assignment.is_completed = False
    assignment.is_expired = False
    assignment.expired_at = None
    assignment.save(update_fields=['due_date', 'is_completed', 'is_expired', 'expired_at'])
    req.status = 'approved'
    req.resolved_at = timezone.now()
    req.save(update_fields=['status', 'resolved_at'])
    messages.success(request, "Продление одобрено, вариант переоткрыт.")
    return redirect('tutor_assignment_view', assignment_id=assignment.id)


@login_required
@require_POST
def tutor_extension_reject(request, assignment_id, req_id):
    if request.user.role != 'tutor':
        return redirect('login')
    assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user, is_draft=False)
    req = get_object_or_404(AssignmentExtensionRequest, id=req_id, assignment=assignment, status='pending')
    req.status = 'rejected'
    req.resolved_at = timezone.now()
    req.save(update_fields=['status', 'resolved_at'])
    messages.success(request, "Запрос отклонён.")
    return redirect('tutor_assignment_view', assignment_id=assignment.id)
```

- [ ] **Step 3: UI в tutor_assignment_view**

Вверху страницы, если есть pending request:
- показать “Ученик просит +N дней” + комментарий
- кнопки “Одобрить / Отклонить” (POST формы на URL выше)

- [ ] **Step 4: Commit**

```bash
git add core/urls.py core/views.py core/templates/core/tutor_assignment_view.html
git commit -m "feat: tutor can approve/reject extension requests and reopen assignment"
```

---

### Task 6: Показ дедлайна ученику в списке вариантов

**Files:**
- Modify: `/workspace/core/templates/core/student_dashboard.html`

- [ ] **Step 1: Вывести due_date**

В карточке assignment добавить строку:
- “Срок: DD.MM.YYYY” если `assignment.due_date`

- [ ] **Step 2: Commit**

```bash
git add core/templates/core/student_dashboard.html
git commit -m "ui: show assignment due date on student dashboard"
```

---

### Task 7: Тесты дедлайна и переоткрытия

**Files:**
- Create: `/workspace/core/tests/test_assignment_deadlines.py`

- [ ] **Step 1: Тест автозакрытия**

Создать тест, который:
- создаёт tutor/student, assignment с due_date вчера, пару задач
- вызывает страницу (например `student_dashboard`)
- проверяет, что assignment стал `is_completed=True`, `is_expired=True`, и есть submission’ы с 0

- [ ] **Step 2: Тест approve переоткрытия**

Создать pending request, вызвать approve endpoint, проверить:
- assignment `is_completed=False`, `is_expired=False`, `due_date` увеличилась

- [ ] **Step 3: Запуск**

```bash
python manage.py test core.tests.test_assignment_deadlines -v 2
```

- [ ] **Step 4: Commit**

```bash
git add core/tests/test_assignment_deadlines.py
git commit -m "test: deadlines auto-close and reopen via extension"
```

---

### Task 8: Финальная проверка и push

- [ ] **Step 1: Миграции**

```bash
python manage.py migrate --noinput
```

- [ ] **Step 2: Compileall**

```bash
python -m compileall -q /workspace/core
```

- [ ] **Step 3: Push**

```bash
git push origin main
```

