# Task Error Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить кнопку `Ошибка` для задач в тренажёре, SRS, решении варианта и журналах, а также отдельный раздел `Ошибки` в `platform-admin`.

**Architecture:** Храним пометки в новой модели `TaskErrorReport` с идемпотентным созданием через единый POST endpoint. UI на ученических и репетиторских экранах использует один и тот же POST API и одинаковое состояние кнопки. `platform-admin` получает отдельные list/detail/update views по существующему паттерну админ-панели.

**Tech Stack:** Django views, Django ORM, Django templates, Tailwind, встроенный Django TestCase, migrations.

---

### Task 1: Модель пометок и единый API

**Files:**
- Modify: `core/models.py`
- Modify: `core/views.py`
- Modify: `core/urls.py`
- Create: `core/migrations/0062_taskerrorreport.py`
- Create: `core/tests/test_task_error_report_api.py`

- [ ] **Step 1: Write the failing tests**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class TaskErrorReportApiTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        self.task_type = TaskType.objects.create(exam_format=self.exam, number=1, name="Тест", max_points=1)
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")
        self.task = Task.objects.create(
            topic=self.topic,
            task_type=self.task_type,
            correct_answer="7",
            difficulty=10,
            exam_points=1,
        )
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.admin = User.objects.create_user(username="a", password="pass", role="admin")
        self.tutor.students.add(self.student)
        self.assignment = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="Вариант",
            is_draft=False,
            exam_format=self.exam,
        )
        self.assignment.tasks.add(self.task)
        self.submission = Submission.objects.create(
            student=self.student,
            task=self.task,
            assignment=self.assignment,
            user_answer="0",
            is_correct=False,
            score=0,
        )

    def test_student_can_create_report(self):
        self.client.force_login(self.student)
        res = self.client.post(
            reverse("report_task_error", args=[self.task.id]),
            {"source": "practice"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertJSONEqual(
            res.content,
            {"ok": True, "created": True, "already_reported": False, "report_id": 1},
        )

    def test_second_click_is_idempotent(self):
        self.client.force_login(self.student)
        url = reverse("report_task_error", args=[self.task.id])
        self.client.post(url, {"source": "variant", "assignment_id": self.assignment.id, "submission_id": self.submission.id})
        res = self.client.post(url, {"source": "variant", "assignment_id": self.assignment.id, "submission_id": self.submission.id})
        self.assertEqual(res.status_code, 200)
        self.assertJSONEqual(
            res.content,
            {"ok": True, "created": False, "already_reported": True, "report_id": 1},
        )

    def test_tutor_can_create_report_for_student_history_context(self):
        self.client.force_login(self.tutor)
        res = self.client.post(
            reverse("report_task_error", args=[self.task.id]),
            {"source": "tutor_history", "submission_id": self.submission.id, "assignment_id": self.assignment.id},
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '"created": true', status_code=200)

    def test_admin_cannot_create_report(self):
        self.client.force_login(self.admin)
        res = self.client.post(reverse("report_task_error", args=[self.task.id]), {"source": "practice"})
        self.assertEqual(res.status_code, 403)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_task_error_report_api -v 2`

Expected: FAIL with `NoReverseMatch: 'report_task_error'` and missing `TaskErrorReport`.

- [ ] **Step 3: Write minimal implementation**

```python
class TaskErrorReport(models.Model):
    REPORTER_ROLE_CHOICES = [
        ("student", "Ученик"),
        ("tutor", "Репетитор"),
    ]
    SOURCE_CHOICES = [
        ("practice", "Тренажер"),
        ("srs", "Интервальные повторения"),
        ("variant", "Вариант"),
        ("student_history", "Журнал ученика"),
        ("tutor_history", "Журнал репетитора"),
    ]
    STATUS_CHOICES = [
        ("new", "Новая"),
        ("reviewed", "Просмотрена"),
        ("resolved", "Решена"),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="error_reports")
    reported_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="task_error_reports")
    reporter_role = models.CharField(max_length=20, choices=REPORTER_ROLE_CHOICES)
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES)
    submission = models.ForeignKey(Submission, on_delete=models.SET_NULL, null=True, blank=True, related_name="task_error_reports")
    assignment = models.ForeignKey(Assignment, on_delete=models.SET_NULL, null=True, blank=True, related_name="task_error_reports")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["task", "reported_by", "reporter_role", "source", "submission", "assignment"],
                name="uniq_task_error_report_context",
            )
        ]


@login_required
@require_POST
def report_task_error(request, task_id):
    if request.user.role not in {"student", "tutor"}:
        return JsonResponse({"error": "forbidden"}, status=403)

    task = get_object_or_404(Task, id=task_id)
    source = (request.POST.get("source") or "").strip()
    if source not in {"practice", "srs", "variant", "student_history", "tutor_history"}:
        return JsonResponse({"error": "invalid_source"}, status=400)

    submission = None
    submission_id = (request.POST.get("submission_id") or "").strip()
    if submission_id.isdigit():
        submission = Submission.objects.filter(id=int(submission_id), task=task).first()

    assignment = None
    assignment_id = (request.POST.get("assignment_id") or "").strip()
    if assignment_id.isdigit():
        assignment = Assignment.objects.filter(id=int(assignment_id)).first()

    try:
        report, created = TaskErrorReport.objects.get_or_create(
            task=task,
            reported_by=request.user,
            reporter_role=request.user.role,
            source=source,
            submission=submission,
            assignment=assignment,
            defaults={"status": "new"},
        )
    except IntegrityError:
        report = TaskErrorReport.objects.get(
            task=task,
            reported_by=request.user,
            reporter_role=request.user.role,
            source=source,
            submission=submission,
            assignment=assignment,
        )
        created = False

    return JsonResponse(
        {
            "ok": True,
            "created": created,
            "already_reported": not created,
            "report_id": report.id,
        }
    )
```

```python
path("api/tasks/<int:task_id>/report-error/", views.report_task_error, name="report_task_error"),
```

Migration skeleton:

```python
class Migration(migrations.Migration):
    dependencies = [
        ("core", "0061_spacedrepetition_fsrs_fields"),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_task_error_report_api -v 2`

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add core/models.py core/views.py core/urls.py core/migrations/0062_taskerrorreport.py core/tests/test_task_error_report_api.py
git commit -m "feat: add task error report api"
```

### Task 2: Кнопка `Ошибка` в тренажёре и в решении варианта

**Files:**
- Modify: `core/views.py`
- Modify: `core/templates/core/student_practice.html`
- Modify: `core/templates/core/student_solve_assignment.html`
- Create: `core/tests/test_student_task_error_buttons.py`

- [ ] **Step 1: Write the failing tests**

```python
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Assignment, ExamFormat, SpacedRepetition, Subject, Task, TaskType, TaskVariant, Topic, User


class StudentTaskErrorButtonsTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.tutor.students.add(self.student)
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="1", difficulty=10, exam_points=1)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=exam)
        self.assignment.tasks.add(self.task)
        SpacedRepetition.objects.create(student=self.student, task=self.task, next_review_date=timezone.localdate())

    def test_practice_page_contains_error_button(self):
        self.client.force_login(self.student)
        res = self.client.get(reverse("student_practice"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Ошибка")
        self.assertContains(res, 'data-error-source="practice"')

    def test_srs_page_contains_error_button(self):
        self.client.force_login(self.student)
        res = self.client.get(reverse("student_practice") + "?mode=srs")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'data-error-source="srs"')

    def test_assignment_page_contains_per_task_error_button(self):
        self.client.force_login(self.student)
        res = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "data-error-source=\"variant\"")
        self.assertContains(res, f"data-task-id=\"{self.task.id}\"")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_student_task_error_buttons -v 2`

Expected: FAIL because `data-error-source` is absent.

- [ ] **Step 3: Write minimal implementation**

Add helper logic near the affected views:

```python
def _reported_task_ids_for_user(*, user, source, task_ids, assignment_id=None):
    qs = TaskErrorReport.objects.filter(
        reported_by=user,
        reporter_role=user.role,
        source=source,
        task_id__in=list(task_ids),
    )
    if assignment_id is None:
        qs = qs.filter(assignment__isnull=True)
    else:
        qs = qs.filter(assignment_id=assignment_id)
    return set(qs.values_list("task_id", flat=True))
```

In `student_practice()` context:

```python
practice_error_reported = False
if task is not None:
    practice_error_reported = TaskErrorReport.objects.filter(
        task=task,
        reported_by=request.user,
        reporter_role=request.user.role,
        source="srs" if mode == "srs" else "practice",
        assignment__isnull=True,
    ).exists()
```

In `student_solve_assignment()` render helper:

```python
variant_reported_ids = _reported_task_ids_for_user(
    user=request.user,
    source="variant",
    task_ids=[t.id for t in tasks_list],
    assignment_id=assignment.id,
)
for task in tasks_list:
    task.error_reported = task.id in variant_reported_ids
```

In `student_practice.html` add one reusable button block:

```html
<button
    type="button"
    class="js-task-error-btn text-red-600 hover:text-red-700 transition flex items-center text-sm font-bold bg-white border border-red-200 px-3 py-2 rounded-lg"
    data-task-id="{{ task.id }}"
    data-error-source="{% if mode == 'srs' %}srs{% else %}practice{% endif %}"
    data-error-reported="{% if practice_error_reported %}1{% else %}0{% endif %}"
>
    <i class="fas fa-exclamation-circle mr-2"></i>
    <span>{% if practice_error_reported %}Ошибка отмечена{% else %}Ошибка{% endif %}</span>
</button>
```

In `student_solve_assignment.html` add per-task button:

```html
<button
    type="button"
    class="js-task-error-btn bg-white border border-red-200 text-red-700 hover:bg-red-50 px-3 py-1 rounded-lg text-xs font-bold transition"
    data-task-id="{{ task.id }}"
    data-error-source="variant"
    data-assignment-id="{{ assignment.id }}"
    data-submission-id="{{ task.saved_submission.id|default:'' }}"
    data-error-reported="{% if task.error_reported %}1{% else %}0{% endif %}"
>
    {% if task.error_reported %}Ошибка отмечена{% else %}Ошибка{% endif %}
</button>
```

Add one shared JS pattern inside each template:

```javascript
async function reportTaskError(btn) {
    if (!btn || btn.dataset.errorReported === '1') return;
    const taskId = btn.dataset.taskId;
    const formData = new FormData();
    formData.append('source', btn.dataset.errorSource || '');
    if (btn.dataset.assignmentId) formData.append('assignment_id', btn.dataset.assignmentId);
    if (btn.dataset.submissionId) formData.append('submission_id', btn.dataset.submissionId);

    const res = await fetch(`/api/tasks/${taskId}/report-error/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': '{{ csrf_token }}' },
        body: formData,
        credentials: 'same-origin',
    });
    if (!res.ok) {
        alert('Не удалось отметить ошибку');
        return;
    }
    btn.dataset.errorReported = '1';
    const label = btn.querySelector('span') || btn;
    label.textContent = 'Ошибка отмечена';
    btn.disabled = true;
    btn.classList.add('opacity-70', 'cursor-not-allowed');
}

document.addEventListener('click', (e) => {
    const btn = e.target.closest('.js-task-error-btn');
    if (!btn) return;
    e.preventDefault();
    reportTaskError(btn);
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_student_task_error_buttons -v 2`

Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/templates/core/student_practice.html core/templates/core/student_solve_assignment.html core/tests/test_student_task_error_buttons.py
git commit -m "feat: add task error buttons to student practice and assignments"
```

### Task 3: Кнопка `Ошибка` в журналах ученика и репетитора

**Files:**
- Modify: `core/views.py`
- Modify: `core/templates/core/student_history.html`
- Modify: `core/templates/core/tutor_student_history.html`
- Create: `core/tests/test_history_task_error_buttons.py`

- [ ] **Step 1: Write the failing tests**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Submission, Task, TaskType, TaskVariant, Topic, User


class HistoryTaskErrorButtonsTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.tutor.students.add(self.student)
        subject = Subject.objects.create(name="Физика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="1", exam_points=1)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="Вариант", is_draft=False, exam_format=exam)
        self.assignment.tasks.add(self.task)
        self.submission = Submission.objects.create(student=self.student, task=self.task, assignment=self.assignment, user_answer="0", is_correct=False, score=0)

    def test_student_history_contains_error_button(self):
        self.client.force_login(self.student)
        res = self.client.get(reverse("student_history"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'data-error-source="student_history"')
        self.assertContains(res, f'data-submission-id="{self.submission.id}"')

    def test_tutor_history_contains_error_button(self):
        self.client.force_login(self.tutor)
        res = self.client.get(reverse("tutor_student_history", args=[self.student.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'data-error-source="tutor_history"')
        self.assertContains(res, f'data-submission-id="{self.submission.id}"')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_history_task_error_buttons -v 2`

Expected: FAIL because history templates do not render the button.

- [ ] **Step 3: Write minimal implementation**

In `student_history()`:

```python
reported_submission_ids = set(
    TaskErrorReport.objects.filter(
        reported_by=request.user,
        reporter_role=request.user.role,
        source="student_history",
        submission_id__in=[s.id for s in submissions],
    ).values_list("submission_id", flat=True)
)
for sub in submissions:
    sub.error_reported = sub.id in reported_submission_ids
```

In `tutor_student_history()`:

```python
reported_submission_ids = set(
    TaskErrorReport.objects.filter(
        reported_by=request.user,
        reporter_role=request.user.role,
        source="tutor_history",
        submission_id__in=[s.id for s in submissions],
    ).values_list("submission_id", flat=True)
)
for sub in submissions:
    sub.error_reported = sub.id in reported_submission_ids
```

In `student_history.html` add button inside each submission card:

```html
<button
    type="button"
    class="js-task-error-btn mt-3 text-xs font-bold bg-white border border-red-200 text-red-700 hover:bg-red-50 px-3 py-2 rounded-lg transition"
    data-task-id="{{ sub.task.id }}"
    data-error-source="student_history"
    data-submission-id="{{ sub.id }}"
    data-assignment-id="{{ sub.assignment_id|default:'' }}"
    data-error-reported="{% if sub.error_reported %}1{% else %}0{% endif %}"
>
    {% if sub.error_reported %}Ошибка отмечена{% else %}Ошибка{% endif %}
</button>
```

In `tutor_student_history.html` add the same button in both assignment and practice detail blocks:

```html
<button
    type="button"
    class="js-task-error-btn bg-white border border-red-200 text-red-700 hover:bg-red-50 px-3 py-2 rounded-lg text-xs font-bold transition"
    data-task-id="{{ sub.task.id }}"
    data-error-source="tutor_history"
    data-submission-id="{{ sub.id }}"
    data-assignment-id="{{ sub.assignment_id|default:'' }}"
    data-error-reported="{% if sub.error_reported %}1{% else %}0{% endif %}"
>
    {% if sub.error_reported %}Ошибка отмечена{% else %}Ошибка{% endif %}
</button>
```

Reuse the same `reportTaskError(btn)` JS pattern already added in Task 2 rather than inventing another transport.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_history_task_error_buttons -v 2`

Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/templates/core/student_history.html core/templates/core/tutor_student_history.html core/tests/test_history_task_error_buttons.py
git commit -m "feat: add task error buttons to history screens"
```

### Task 4: Раздел `Ошибки` в `platform-admin`

**Files:**
- Modify: `core/views.py`
- Modify: `core/urls.py`
- Modify: `core/templates/core/admin_dashboard.html`
- Modify: `core/templates/core/admin_exam_structure.html`
- Modify: `core/templates/core/admin_reshuege_import.html`
- Modify: `core/templates/core/admin_system.html`
- Modify: `core/templates/core/admin_openrouter_balance.html`
- Create: `core/templates/core/admin_task_error_reports.html`
- Create: `core/templates/core/admin_task_error_report_detail.html`
- Create: `core/tests/test_admin_task_error_reports.py`

- [ ] **Step 1: Write the failing tests**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Subject, Topic, Task, User, TaskErrorReport


class AdminTaskErrorReportsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="a", password="pass", role="admin")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        subject = Subject.objects.create(name="Математика")
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, correct_answer="1", exam_points=1)
        self.report = TaskErrorReport.objects.create(
            task=task,
            reported_by=self.tutor,
            reporter_role="tutor",
            source="tutor_history",
            status="new",
        )

    def test_requires_admin(self):
        self.client.force_login(self.tutor)
        res = self.client.get(reverse("admin_task_error_reports"))
        self.assertIn(res.status_code, (302, 403))

    def test_admin_can_open_list_page(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("admin_task_error_reports"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Ошибки")
        self.assertContains(res, str(self.report.id))

    def test_admin_can_update_status(self):
        self.client.force_login(self.admin)
        res = self.client.post(
            reverse("admin_task_error_report_update", args=[self.report.id]),
            {"status": "resolved"},
        )
        self.assertEqual(res.status_code, 302)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "resolved")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_admin_task_error_reports -v 2`

Expected: FAIL with `NoReverseMatch` for admin error routes.

- [ ] **Step 3: Write minimal implementation**

Add admin views:

```python
@login_required
def admin_task_error_reports(request):
    if request.user.role != "admin":
        return redirect("login")

    qs = TaskErrorReport.objects.select_related("task", "reported_by", "submission", "assignment").order_by("-created_at")
    status_filter = (request.GET.get("status") or "").strip()
    source_filter = (request.GET.get("source") or "").strip()
    role_filter = (request.GET.get("role") or "").strip()
    search_query = (request.GET.get("q") or "").strip()

    if status_filter:
        qs = qs.filter(status=status_filter)
    if source_filter:
        qs = qs.filter(source=source_filter)
    if role_filter:
        qs = qs.filter(reporter_role=role_filter)
    search_task_id = int(search_query) if search_query.isdigit() else None
    if search_query:
        qs = qs.filter(
            Q(task_id=search_task_id) |
            Q(reported_by__username__icontains=search_query) |
            Q(reported_by__first_name__icontains=search_query) |
            Q(reported_by__last_name__icontains=search_query)
        )

    page_obj = Paginator(qs, 25).get_page(request.GET.get("page", 1))
    return render(
        request,
        "core/admin_task_error_reports.html",
        {
            "page_obj": page_obj,
            "reports": list(page_obj.object_list),
            "status_filter": status_filter,
            "source_filter": source_filter,
            "role_filter": role_filter,
            "search_query": search_query,
        },
    )


@login_required
def admin_task_error_report_detail(request, report_id):
    if request.user.role != "admin":
        return redirect("login")
    report = get_object_or_404(
        TaskErrorReport.objects.select_related("task", "reported_by", "submission", "assignment"),
        id=report_id,
    )
    return render(request, "core/admin_task_error_report_detail.html", {"report": report})


@login_required
@require_POST
def admin_task_error_report_update(request, report_id):
    if request.user.role != "admin":
        return HttpResponseForbidden()
    report = get_object_or_404(TaskErrorReport, id=report_id)
    status = (request.POST.get("status") or "").strip()
    if status not in {"new", "reviewed", "resolved"}:
        return redirect("admin_task_error_report_detail", report_id=report.id)
    report.status = status
    report.save(update_fields=["status", "updated_at"])
    return redirect("admin_task_error_report_detail", report_id=report.id)
```

Add URLs:

```python
path("platform-admin/errors/", views.admin_task_error_reports, name="admin_task_error_reports"),
path("platform-admin/errors/<int:report_id>/", views.admin_task_error_report_detail, name="admin_task_error_report_detail"),
path("platform-admin/errors/<int:report_id>/update/", views.admin_task_error_report_update, name="admin_task_error_report_update"),
```

Add menu item to every existing admin template:

```html
<a href="{% url 'admin_task_error_reports' %}" class="flex items-center px-4 py-3 text-gray-400 hover:bg-gray-800 hover:text-white rounded-lg transition">
    <i class="fas fa-exclamation-triangle w-6 text-gray-400"></i> Ошибки
</a>
```

List page table row:

```html
<tr>
    <td class="px-6 py-4"><a href="{% url 'admin_task_error_report_detail' report.id %}" class="text-primary font-bold hover:underline">#{{ report.id }}</a></td>
    <td class="px-6 py-4">{{ report.created_at|date:"d.m.Y H:i" }}</td>
    <td class="px-6 py-4">Task {{ report.task_id }}</td>
    <td class="px-6 py-4">{{ report.reported_by.get_full_name|default:report.reported_by.username }}</td>
    <td class="px-6 py-4">{{ report.get_reporter_role_display }}</td>
    <td class="px-6 py-4">{{ report.get_source_display }}</td>
    <td class="px-6 py-4">{{ report.get_status_display }}</td>
</tr>
```

Detail page status form:

```html
<form method="POST" action="{% url 'admin_task_error_report_update' report.id %}">
    {% csrf_token %}
    <select name="status" class="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white">
        <option value="new" {% if report.status == 'new' %}selected{% endif %}>Новая</option>
        <option value="reviewed" {% if report.status == 'reviewed' %}selected{% endif %}>Просмотрена</option>
        <option value="resolved" {% if report.status == 'resolved' %}selected{% endif %}>Решена</option>
    </select>
    <button type="submit" class="bg-primary text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-indigo-700 transition">
        Сохранить статус
    </button>
</form>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_admin_task_error_reports -v 2`

Expected: PASS, 3 tests.

- [ ] **Step 5: Run the focused regression suite**

Run: `python manage.py test core.tests.test_task_error_report_api core.tests.test_student_task_error_buttons core.tests.test_history_task_error_buttons core.tests.test_admin_task_error_reports -v 2`

Expected: PASS for all new tests.

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/urls.py core/templates/core/admin_dashboard.html core/templates/core/admin_exam_structure.html core/templates/core/admin_reshuege_import.html core/templates/core/admin_system.html core/templates/core/admin_openrouter_balance.html core/templates/core/admin_task_error_reports.html core/templates/core/admin_task_error_report_detail.html core/tests/test_admin_task_error_reports.py
git commit -m "feat: add task error reports to platform admin"
```
