# Exam-Scoped SRS + Tags + Moderation Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В `student_practice?mode=srs` выдавать задачи строго внутри активного `ExamFormat`, подбирать “новую” задачу по слабым тегам, и поддержать очередь ручной модерации по запросу ученика с заморозкой SRS до решения.

**Architecture:** Используем существующие `SpacedRepetition` (SM-2) и `Task.ai_tags`. Добавляем очередь модерации для `Submission` (главным образом SRS-режим для развёрнутых задач). Расширяем выбор задач в SRS-режиме: сначала due, иначе новая задача внутри экзамена по теговой слабости.

**Tech Stack:** Django 6, PostgreSQL, Django templates + fetch (JS), pytest.

---

## Map of Relevant Files

- Modify: [models.py](file:///workspace/core/models.py)
- Create: `core/migrations/0059_submission_review_queue.py`
- Modify: [services.py](file:///workspace/core/services.py)
- Modify: [views.py](file:///workspace/core/views.py)
- Modify: [student_practice.html](file:///workspace/core/templates/core/student_practice.html)
- Create/Modify: `core/templates/core/tutor_review_queue.html`
- Modify: [urls.py](file:///workspace/core/urls.py)
- Modify/Add tests in: `/workspace/core/tests/`

---

### Task 1: Add Moderation Queue Model + Finalization Flag

**Files:**
- Modify: [models.py](file:///workspace/core/models.py)
- Create: `/workspace/core/migrations/0059_submission_review_queue.py`

- [ ] **Step 1: Write failing test for new model presence**

Create: `/workspace/core/tests/test_submission_review_queue_model.py`

```python
import pytest
from django.apps import apps

@pytest.mark.django_db
def test_submission_review_request_model_exists():
    model = apps.get_model("core", "SubmissionReviewRequest")
    assert model is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest /workspace/core/tests/test_submission_review_queue_model.py -q
```

Expected: FAIL (model not found).

- [ ] **Step 3: Add model + migration**

Update: `/workspace/core/models.py` (add near `Submission` model):

```python
class SubmissionReviewRequest(models.Model):
    STATUS_CHOICES = [
        ("queued", "В очереди"),
        ("resolved", "Решено"),
    ]

    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, related_name="review_request")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_submission_review_requests")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_submission_review_requests",
    )

    verdict_is_correct = models.BooleanField(null=True, blank=True)
    verdict_primary_score = models.IntegerField(null=True, blank=True)
    verdict_note = models.TextField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]
```

Also add to `Submission`:

```python
ai_verdict_finalized_at = models.DateTimeField(null=True, blank=True, db_index=True)
```

Create migration `0059_submission_review_queue.py` with `CreateModel` + `AddField`.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest /workspace/core/tests/test_submission_review_queue_model.py -q
```

Expected: PASS.

---

### Task 2: Exam-Scoped Due Query + “New Task” Selection by Weak Tags

**Files:**
- Modify: [services.py](file:///workspace/core/services.py)
- Modify: [views.py](file:///workspace/core/views.py)
- Test: `/workspace/core/tests/test_srs_exam_scoped_selection.py`

- [ ] **Step 1: Write failing tests**

Create: `/workspace/core/tests/test_srs_exam_scoped_selection.py`

```python
import pytest
from django.utils import timezone
from core.models import User, Subject, ExamFormat, TaskType, Topic, Task, TaskVariant, SpacedRepetition
from core.services import get_due_tasks_for_student

@pytest.mark.django_db
def test_get_due_tasks_for_student_filters_by_exam_format():
    student = User.objects.create(username="s", role="student")
    subj = Subject.objects.create(name="Математика")
    ef1 = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
    ef2 = ExamFormat.objects.create(subject=subj, name="ОГЭ", year=2026, is_active=True)
    tt1 = TaskType.objects.create(exam_format=ef1, number=1, name="t1", max_points=1)
    tt2 = TaskType.objects.create(exam_format=ef2, number=1, name="t2", max_points=1)
    top = Topic.objects.create(subject=subj, name="T")
    task1 = Task.objects.create(topic=top, task_type=tt1, correct_answer="1", difficulty=50, exam_points=1)
    task2 = Task.objects.create(topic=top, task_type=tt2, correct_answer="1", difficulty=50, exam_points=1)
    TaskVariant.objects.create(task=task1, theme="classic", content="x", solution="")
    TaskVariant.objects.create(task=task2, theme="classic", content="x", solution="")
    today = timezone.now().date()
    SpacedRepetition.objects.create(student=student, task=task1, next_review_date=today)
    SpacedRepetition.objects.create(student=student, task=task2, next_review_date=today)

    qs = get_due_tasks_for_student(student, exam_format_id=ef1.id)
    ids = list(qs.values_list("task_id", flat=True))
    assert ids == [task1.id]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest /workspace/core/tests/test_srs_exam_scoped_selection.py::test_get_due_tasks_for_student_filters_by_exam_format -q
```

Expected: FAIL (signature/behavior not implemented).

- [ ] **Step 3: Implement `get_due_tasks_for_student(student, exam_format_id=None)`**

Update: `/workspace/core/services.py`

```python
def get_due_tasks_for_student(student, exam_format_id=None):
    qs = SpacedRepetition.objects.filter(
        student=student,
        next_review_date__lte=timezone.now().date(),
    ).order_by("next_review_date")
    if exam_format_id:
        qs = qs.filter(task__task_type__exam_format_id=int(exam_format_id))
    return qs
```

- [ ] **Step 4: Add “new task” selection helper (MVP)**

Update: `/workspace/core/services.py` (new helper, used only by views):

```python
from django.db.models import Count, Case, When, IntegerField, Sum

def _tag_weakness_for_student(student, exam_format_id):
    rows = (
        TaskLog.objects
        .filter(student=student, task__task_type__exam_format_id=int(exam_format_id))
        .exclude(task__ai_tags__isnull=True)
        .values("task__ai_tags")
        .annotate(
            total=Count("id"),
            correct=Sum(
                Case(
                    When(score__gt=0, then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            ),
        )
    )
    out = {}
    for r in rows:
        tag_id = r["task__ai_tags"]
        total = int(r["total"] or 0)
        correct = int(r["correct"] or 0)
        # сглаживание: +1/+2
        rate = (correct + 1) / (total + 2) if total >= 0 else 0.5
        out[int(tag_id)] = 1.0 - float(rate)
    return out

def get_new_task_for_student_srs(student, exam_format_id, limit=300):
    weakness = _tag_weakness_for_student(student, exam_format_id)
    qs = (
        Task.objects
        .filter(task_type__exam_format_id=int(exam_format_id))
        .exclude(task_logs__student=student)
        .prefetch_related("ai_tags")
        .select_related("task_type", "task_type__exam_format", "topic", "topic__subject")
        .order_by("id")
    )
    candidates = list(qs[: int(limit)])
    if not candidates:
        return None
    best = None
    best_score = None
    for t in candidates:
        s = 0.0
        tags = list(getattr(t, "ai_tags", []).all()) if hasattr(t, "ai_tags") else []
        for tg in tags:
            s += float(weakness.get(int(tg.id), 0.0))
        if best is None or s > best_score:
            best = t
            best_score = s
    return best
```

If no tag stats exist, `weakness` будет пустым и score=0; тогда выбирается первая из кандидатов (это допустимо для MVP).

- [ ] **Step 5: Wire into `student_practice` for mode=srs**

Update: `/workspace/core/views.py` in `student_practice` GET branch:

- Determine active `StudentSubjectProfile` even for `mode == "srs"` (reuse existing logic from `student_dashboard`/practice non-srs).
- Get `exam_format_id = getattr(active_profile, "exam_format_id", None)` and require it for strictness.
- Replace:

```python
due_qs = get_due_tasks_for_student(request.user).select_related("task")
```

with:

```python
due_qs = get_due_tasks_for_student(request.user, exam_format_id=exam_format_id).select_related("task")
```

- When `due` is empty, call `get_new_task_for_student_srs(...)` to pick task and ensure it is present in SRS:

```python
task = get_new_task_for_student_srs(request.user, exam_format_id=exam_format_id)
if task:
    SpacedRepetition.objects.get_or_create(student=request.user, task=task, defaults={"next_review_date": timezone.now().date()})
```

- [ ] **Step 6: Run tests**

Run:

```bash
pytest /workspace/core/tests/test_srs_exam_scoped_selection.py -q
```

Expected: PASS.

---

### Task 3: Defer SRS/Xp Update Until Student Accepts (SRS Extended AI Verify)

**Files:**
- Modify: [views.py](file:///workspace/core/views.py)
- Modify: [student_practice.html](file:///workspace/core/templates/core/student_practice.html)
- Test: update existing AI verify tests (see below)

- [ ] **Step 1: Add failing test for “verify does not finalize”**

Create: `/workspace/core/tests/test_ai_verify_requires_finalize_for_srs.py`

```python
import pytest
from django.utils import timezone
from core.models import User, Subject, ExamFormat, TaskType, Topic, Task, TaskVariant, Submission, SpacedRepetition

@pytest.mark.django_db
def test_ai_verify_does_not_touch_srs_until_finalize(client, settings, monkeypatch):
    student = User.objects.create_user(username="s", password="pw", role="student")
    client.force_login(student)
    subj = Subject.objects.create(name="Математика")
    ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
    tt = TaskType.objects.create(exam_format=ef, number=13, name="t", max_points=2, is_extended_answer=True)
    top = Topic.objects.create(subject=subj, name="T")
    task = Task.objects.create(topic=top, task_type=tt, correct_answer="x", difficulty=50, exam_points=2)
    TaskVariant.objects.create(task=task, theme="classic", content="x", solution="")

    sub = Submission.objects.create(student=student, task=task, is_correct=None, primary_score=0)
    SpacedRepetition.objects.create(student=student, task=task, next_review_date=timezone.now().date())

    # mock: make verify endpoint return quickly without calling upstream
    settings.OPENROUTER_API_KEY = "x"
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    # Implementation detail: in real tests reuse existing mocking pattern from repo
    assert True
```

This test is a placeholder to be replaced by adapting existing AI verify tests in repo (preferred). The key acceptance check in updated tests should be:
- after POST `/api/submission/<id>/verify/`, `SpacedRepetition` is unchanged and `Submission.ai_verdict_finalized_at is None`.

- [ ] **Step 2: Refactor `api_verify_with_ai` to only persist AI fields**

Update: `/workspace/core/views.py` in `api_verify_with_ai`:
- keep “call OpenRouter + parse JSON + save AI fields”
- remove XP/SRS updates from this endpoint
- ensure it does **not** call `process_task_submission`
- return payload without `xp_gained` (or return 0) and include a flag like `needs_finalize: true`

- [ ] **Step 3: Add endpoint `api_submission_finalize_verdict`**

Add in `/workspace/core/views.py`:

```python
@login_required
@require_POST
def api_submission_finalize_verdict(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id, student=request.user)
    if getattr(submission, "ai_verdict_finalized_at", None):
        return JsonResponse({"status": "ok", "already_finalized": True})
    if hasattr(submission, "review_request") and submission.review_request and submission.review_request.status == "queued":
        return JsonResponse({"error": "pending_review"}, status=400)
    # compute grade from submission.is_correct / primary_score
    # apply XP and SRS (reusing existing logic from api_verify_with_ai)
    # set submission.ai_verdict_finalized_at = now
```

Move the shared logic for XP+SRS into a small helper function inside `views.py` (or `services.py`) to avoid duplication between finalize and tutor resolve.

- [ ] **Step 4: Update SRS UI in `student_practice.html`**

Update JS for `verifySrsWithAI`:
- after showing verdict, show 2 buttons:
  - “Следующая задача” calls `/api/submission/<id>/finalize/` then redirects to `student_practice?mode=srs`
  - “Отправить на модерацию” calls `/api/submission/<id>/request-review/` then redirects to `student_practice?mode=srs`

Example JS snippet:

```js
async function finalizeAndNext(submissionId) {
  await fetch(`/api/submission/${submissionId}/finalize/`, { method: 'POST', headers: { 'X-CSRFToken': '{{ csrf_token }}' }});
  window.location.href = '{% url "student_practice" %}?mode=srs';
}
async function requestReviewAndNext(submissionId) {
  await fetch(`/api/submission/${submissionId}/request-review/`, { method: 'POST', headers: { 'X-CSRFToken': '{{ csrf_token }}' }});
  window.location.href = '{% url "student_practice" %}?mode=srs';
}
```

- [ ] **Step 5: Wire URLs**

Update: `/workspace/core/urls.py` (or `core/urls_chat.py` if relevant; prefer `core/urls.py` where existing submission api routes live):
- add:
  - `path("api/submission/<int:submission_id>/finalize/", views.api_submission_finalize_verdict, name="api_submission_finalize_verdict")`
  - `path("api/submission/<int:submission_id>/request-review/", views.api_submission_request_review, name="api_submission_request_review")`

- [ ] **Step 6: Update/adjust existing tests**

Search and update tests that assert SRS changes after `/verify/` to now assert SRS changes after `/finalize/`.
Likely candidates:
- `test_ai_verify_partial_score_adds_srs.py`
- `test_student_practice_srs_*`

Run:

```bash
pytest /workspace/core/tests/test_ai_verify_partial_score_adds_srs.py -q
```

Expected: initially FAIL → update assertions and helper calls.

---

### Task 4: Student “Request Review” Endpoint

**Files:**
- Modify: [views.py](file:///workspace/core/views.py)
- Test: `/workspace/core/tests/test_submission_request_review.py`

- [ ] **Step 1: Write failing test**

Create: `/workspace/core/tests/test_submission_request_review.py`

```python
import pytest
from core.models import User, Subject, ExamFormat, TaskType, Topic, Task, TaskVariant, Submission, SubmissionReviewRequest

@pytest.mark.django_db
def test_student_can_create_review_request(client):
    student = User.objects.create_user(username="s", password="pw", role="student")
    client.force_login(student)
    subj = Subject.objects.create(name="Математика")
    ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
    tt = TaskType.objects.create(exam_format=ef, number=13, name="t", max_points=2, is_extended_answer=True)
    top = Topic.objects.create(subject=subj, name="T")
    task = Task.objects.create(topic=top, task_type=tt, correct_answer="x", difficulty=50, exam_points=2)
    TaskVariant.objects.create(task=task, theme="classic", content="x", solution="")
    sub = Submission.objects.create(student=student, task=task, is_correct=False, primary_score=0)

    res = client.post(f"/api/submission/{sub.id}/request-review/")
    assert res.status_code == 200
    rr = SubmissionReviewRequest.objects.get(submission=sub)
    assert rr.status == "queued"
    assert rr.created_by_id == student.id
```

- [ ] **Step 2: Implement endpoint**

In `/workspace/core/views.py`:

```python
@login_required
@require_POST
def api_submission_request_review(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id, student=request.user)
    if getattr(submission, "ai_verdict_finalized_at", None):
        return JsonResponse({"error": "already_finalized"}, status=400)
    rr, created = SubmissionReviewRequest.objects.get_or_create(
        submission=submission,
        defaults={"created_by": request.user},
    )
    if not created and rr.status != "queued":
        rr.status = "queued"
        rr.resolved_at = None
        rr.resolved_by = None
        rr.verdict_is_correct = None
        rr.verdict_primary_score = None
        rr.verdict_note = None
        rr.save()
    return JsonResponse({"status": "ok"})
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest /workspace/core/tests/test_submission_request_review.py -q
```

Expected: PASS.

---

### Task 5: Tutor Queue UI + Resolve Flow (Apply Final Verdict and Finalize SRS)

**Files:**
- Modify: [views.py](file:///workspace/core/views.py)
- Modify: [urls.py](file:///workspace/core/urls.py)
- Create: `/workspace/core/templates/core/tutor_review_queue.html`
- Test: `/workspace/core/tests/test_tutor_review_queue_resolve.py`

- [ ] **Step 1: Add failing resolve test**

Create: `/workspace/core/tests/test_tutor_review_queue_resolve.py`

```python
import pytest
from django.utils import timezone
from core.models import User, Subject, ExamFormat, TaskType, Topic, Task, TaskVariant, Submission, SubmissionReviewRequest, SpacedRepetition

@pytest.mark.django_db
def test_tutor_can_resolve_review_and_finalize_srs(client):
    tutor = User.objects.create_user(username="t", password="pw", role="tutor")
    student = User.objects.create_user(username="s", password="pw", role="student")
    tutor.students.add(student)
    client.force_login(tutor)

    subj = Subject.objects.create(name="Математика")
    ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
    tt = TaskType.objects.create(exam_format=ef, number=13, name="t", max_points=2, is_extended_answer=True)
    top = Topic.objects.create(subject=subj, name="T")
    task = Task.objects.create(topic=top, task_type=tt, correct_answer="x", difficulty=50, exam_points=2)
    TaskVariant.objects.create(task=task, theme="classic", content="x", solution="")

    sub = Submission.objects.create(student=student, task=task, is_correct=False, primary_score=0)
    rr = SubmissionReviewRequest.objects.create(submission=sub, created_by=student, status="queued")
    SpacedRepetition.objects.get_or_create(student=student, task=task, defaults={"next_review_date": timezone.now().date()})

    res = client.post(f"/tutor/review-queue/{rr.id}/resolve/", data={"is_correct": "1"})
    assert res.status_code in (200, 302)
    rr.refresh_from_db()
    sub.refresh_from_db()
    assert rr.status == "resolved"
    assert sub.ai_verdict_finalized_at is not None
```

- [ ] **Step 2: Implement tutor list view**

Add in `/workspace/core/views.py`:

```python
@login_required
def tutor_review_queue(request):
    if request.user.role != "tutor":
        return redirect("login")
    qs = (
        SubmissionReviewRequest.objects
        .filter(status="queued")
        .select_related("submission", "submission__student", "submission__task", "submission__task__task_type", "submission__task__task_type__exam_format")
        .order_by("created_at")
    )
    qs = qs.filter(submission__student__in=request.user.students.all())
    return render(request, "core/tutor_review_queue.html", {"items": qs})
```

- [ ] **Step 3: Implement resolve view**

Add in `/workspace/core/views.py`:

```python
@login_required
@require_POST
def tutor_review_queue_resolve(request, request_id):
    if request.user.role != "tutor":
        return redirect("login")
    rr = get_object_or_404(
        SubmissionReviewRequest.objects.select_related("submission", "submission__student", "submission__task", "submission__task__task_type"),
        id=request_id,
        status="queued",
    )
    if not request.user.students.filter(id=rr.submission.student_id).exists():
        return JsonResponse({"error": "forbidden"}, status=403)

    is_correct = (request.POST.get("is_correct") or "").strip() in {"1", "true", "yes"}
    task = rr.submission.task
    max_points = max(int(task.exam_points or 0), int(getattr(task.task_type, "max_points", 0) or 0))
    primary_score = max_points if is_correct else 0

    rr.status = "resolved"
    rr.resolved_at = timezone.now()
    rr.resolved_by = request.user
    rr.verdict_is_correct = is_correct
    rr.verdict_primary_score = primary_score
    rr.save()

    # apply verdict to submission
    rr.submission.is_correct = is_correct
    rr.submission.primary_score = primary_score
    rr.submission.save(update_fields=["is_correct", "primary_score"])

    # finalize SRS + XP (reuse helper from Task 3)
    _finalize_submission_verdict(student=rr.submission.student, submission=rr.submission)

    return redirect("tutor_review_queue")
```

- [ ] **Step 4: Add URLs**

Update `/workspace/core/urls.py`:

```python
path("tutor/review-queue/", views.tutor_review_queue, name="tutor_review_queue"),
path("tutor/review-queue/<int:request_id>/resolve/", views.tutor_review_queue_resolve, name="tutor_review_queue_resolve"),
```

- [ ] **Step 5: Add template**

Create: `/workspace/core/templates/core/tutor_review_queue.html`

```html
{% extends "core/tutor_dashboard.html" %}
{% block content %}
<div class="p-6">
  <h1 class="text-2xl font-bold mb-4">Очередь проверок</h1>
  {% if items %}
    <div class="space-y-4">
      {% for r in items %}
        <div class="bg-white border border-gray-200 rounded-xl p-4">
          <div class="text-sm text-gray-600">{{ r.submission.student.username }} · {{ r.submission.task.task_type.label }}</div>
          <div class="mt-2 flex gap-2">
            <form method="POST" action="{% url 'tutor_review_queue_resolve' r.id %}">
              {% csrf_token %}
              <input type="hidden" name="is_correct" value="1">
              <button class="px-3 py-2 bg-green-600 text-white rounded-lg font-bold text-sm">Правильно</button>
            </form>
            <form method="POST" action="{% url 'tutor_review_queue_resolve' r.id %}">
              {% csrf_token %}
              <input type="hidden" name="is_correct" value="0">
              <button class="px-3 py-2 bg-red-600 text-white rounded-lg font-bold text-sm">Неправильно</button>
            </form>
          </div>
        </div>
      {% endfor %}
    </div>
  {% else %}
    <div class="text-gray-500">Пока нет заявок.</div>
  {% endif %}
</div>
{% endblock %}
```

If `tutor_dashboard.html` is not a base template, adapt by copying the standard page shell used in other tutor pages (follow existing pattern).

- [ ] **Step 6: Run tests**

Run:

```bash
pytest /workspace/core/tests/test_tutor_review_queue_resolve.py -q
```

Expected: PASS.

---

## Plan Self-Review

- Spec coverage:
  - Exam-scoped SRS: Task 2
  - “New task” by weak tags: Task 2
  - Manual moderation queue + freeze: Tasks 1, 3, 4, 5
  - Tags/difficulty persistence: already exists in `Task`/batch annotator; plan uses `Task.ai_tags`
- Placeholder scan:
  - One test in Task 3 references adapting existing mocks; during implementation replace it with updating existing repo tests for `api_verify_with_ai` behavior.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-18-exam-srs-tags-and-moderation.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks
2. **Inline Execution** - Execute tasks in this session with checkpoints

Which approach?

