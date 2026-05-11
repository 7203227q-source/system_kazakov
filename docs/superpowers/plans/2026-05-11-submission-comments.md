# Submission Comments (Task Q&A Thread) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-task, per-assignment message thread between student and tutor, attached to `Submission`, with controlled visibility for the student.

**Architecture:** Introduce `SubmissionComment` (FK → `Submission`). Student posts messages from the solve page at any time, but sees the thread there only after pressing “Проверить” (or in history). Tutor can reply in tutor history and in a dedicated tutor assignment view page. Keep existing `Submission` workflow intact.

**Tech Stack:** Django, Tailwind templates, existing `Submission`/`Assignment` models and views.

---

## File Map

**Create**
- `core/tests/test_submission_comments.py`
- `core/templates/core/tutor_assignment_view.html`

**Modify**
- `core/models.py` (add `SubmissionComment`)
- `core/migrations/` (new migration for `SubmissionComment`)
- `core/urls.py` (new endpoints)
- `core/views.py` (new comment endpoints; enrich check JSON; add tutor assignment view; feed comments into contexts)
- `core/templates/core/student_solve_assignment.html` (student “ask tutor” UI + show thread after check)
- `core/templates/core/student_history.html` (show thread in history)
- `core/templates/core/tutor_student_history.html` (show thread + reply)
- `core/templates/core/student_assignment_summary.html` (optional: show thread on summary page)

---

### Task 1: Add `SubmissionComment` model + migration

**Files:**
- Modify: `core/models.py`
- Create: `core/migrations/00xx_submissioncomment.py` (via `makemigrations`)

- [ ] **Step 1: Write failing tests for model wiring**

Create `core/tests/test_submission_comments.py`:

```python
from django.test import TestCase

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, Submission, User


class SubmissionCommentModelTests(TestCase):
    def test_comment_attaches_to_submission(self):
        tutor = User.objects.create(username="t", role="tutor")
        student = User.objects.create(username="s", role="student")
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)
        task = Task.objects.create(topic=topic, task_type=task_type, fipi_id="1", correct_answer="1", difficulty=10, exam_points=1)

        assignment = Assignment.objects.create(tutor=tutor, student=student, title="Вариант 1")
        assignment.tasks.add(task)

        sub = Submission.objects.create(student=student, task=task, assignment=assignment, user_answer="", is_correct=None)
        c = sub.comments.create(author=student, author_role="student", text="Вопрос?")

        self.assertEqual(c.submission_id, sub.id)
        self.assertEqual(sub.comments.count(), 1)
```

- [ ] **Step 2: Run test to confirm it fails**

Run:
```bash
python manage.py test core.tests.test_submission_comments.SubmissionCommentModelTests -v 1
```

Expected: FAIL (`Submission` has no `comments` relation / model missing).

- [ ] **Step 3: Add model to `core/models.py`**

Add below `Submission`:

```python
class SubmissionComment(models.Model):
    ROLE_CHOICES = [
        ("student", "Ученик"),
        ("tutor", "Репетитор"),
    ]

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="submission_comments")
    author_role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["submission", "created_at"]),
        ]
```

- [ ] **Step 4: Create migration**

Run:
```bash
python manage.py makemigrations core
```

Verify the migration contains `SubmissionComment` with the index.

- [ ] **Step 5: Run the model test again**

Run:
```bash
python manage.py test core.tests.test_submission_comments.SubmissionCommentModelTests -v 1
```

Expected: PASS.

---

### Task 2: Add endpoints for posting comments (student + tutor)

**Files:**
- Modify: `core/urls.py`
- Modify: `core/views.py`
- Test: `core/tests/test_submission_comments.py`

- [ ] **Step 1: Write failing permission tests**

Extend `core/tests/test_submission_comments.py`:

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, Submission, User


class SubmissionCommentEndpointTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create(username="t", role="tutor")
        self.student = User.objects.create(username="s", role="student")
        self.other_student = User.objects.create(username="s2", role="student")

        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)
        self.task = Task.objects.create(topic=topic, task_type=task_type, fipi_id="1", correct_answer="1", difficulty=10, exam_points=1)

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="Вариант 1")
        self.assignment.tasks.add(self.task)
        self.sub = Submission.objects.create(student=self.student, task=self.task, assignment=self.assignment, user_answer="", is_correct=None)

    def test_student_can_post_comment_for_own_assignment_task(self):
        self.client.force_login(self.student)
        url = reverse("student_add_submission_comment", args=[self.assignment.id, self.task.id])
        res = self.client.post(url, {"text": "Вопрос"})
        self.assertEqual(res.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.comments.count(), 1)

    def test_student_cannot_post_comment_for_other_student_assignment(self):
        self.client.force_login(self.other_student)
        url = reverse("student_add_submission_comment", args=[self.assignment.id, self.task.id])
        res = self.client.post(url, {"text": "Вопрос"})
        self.assertEqual(res.status_code, 403)

    def test_tutor_can_post_comment_for_own_student_submission(self):
        self.client.force_login(self.tutor)
        url = reverse("tutor_add_submission_comment", args=[self.sub.id])
        res = self.client.post(url, {"text": "Ответ"})
        self.assertEqual(res.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.comments.count(), 1)

    def test_tutor_cannot_post_comment_for_foreign_submission(self):
        tutor2 = User.objects.create(username="t2", role="tutor")
        self.client.force_login(tutor2)
        url = reverse("tutor_add_submission_comment", args=[self.sub.id])
        res = self.client.post(url, {"text": "Ответ"})
        self.assertEqual(res.status_code, 403)
```

- [ ] **Step 2: Run the new tests to confirm failure**

Run:
```bash
python manage.py test core.tests.test_submission_comments.SubmissionCommentEndpointTests -v 1
```

Expected: FAIL (no urls/views).

- [ ] **Step 3: Add URLs**

In `core/urls.py` add:

```python
path(
    "student/assignment/<int:assignment_id>/task/<int:task_id>/comment/",
    views.student_add_submission_comment,
    name="student_add_submission_comment",
),
path(
    "tutor/submission/<int:submission_id>/comment/",
    views.tutor_add_submission_comment,
    name="tutor_add_submission_comment",
),
```

- [ ] **Step 4: Implement views**

In `core/views.py` add:

```python
from django.views.decorators.http import require_POST


@login_required
@require_POST
def student_add_submission_comment(request, assignment_id, task_id):
    if request.user.role != "student":
        return JsonResponse({"error": "forbidden"}, status=403)

    assignment = get_object_or_404(Assignment, id=assignment_id, student=request.user)
    task = get_object_or_404(Task, id=task_id)
    text = (request.POST.get("text") or "").strip()
    if not text:
        return JsonResponse({"error": "empty"}, status=400)

    submission, _ = Submission.objects.get_or_create(student=request.user, assignment=assignment, task=task)
    submission.comments.create(author=request.user, author_role="student", text=text)

    return JsonResponse({"ok": True, "comments_count": submission.comments.count()})


@login_required
@require_POST
def tutor_add_submission_comment(request, submission_id):
    if request.user.role != "tutor":
        return JsonResponse({"error": "forbidden"}, status=403)

    submission = get_object_or_404(Submission.objects.select_related("assignment"), id=submission_id)
    if not submission.assignment or submission.assignment.tutor_id != request.user.id:
        return JsonResponse({"error": "forbidden"}, status=403)

    text = (request.POST.get("text") or "").strip()
    if not text:
        return JsonResponse({"error": "empty"}, status=400)

    submission.comments.create(author=request.user, author_role="tutor", text=text)
    return JsonResponse({"ok": True, "comments_count": submission.comments.count()})
```

- [ ] **Step 5: Run endpoint tests**

Run:
```bash
python manage.py test core.tests.test_submission_comments.SubmissionCommentEndpointTests -v 1
```

Expected: PASS.

---

### Task 3: Expose comments in “Проверить” response and wire student solve UI

**Files:**
- Modify: `core/views.py` (`student_check_assignment_task`, `student_solve_assignment`)
- Modify: `core/templates/core/student_solve_assignment.html`
- Test: `core/tests/test_submission_comments.py`

- [ ] **Step 1: Add failing test for check JSON includes comment flags**

Add to `core/tests/test_submission_comments.py`:

```python
from django.urls import reverse


class SubmissionCheckCommentsResponseTests(TestCase):
    def test_check_returns_comment_flags(self):
        tutor = User.objects.create(username="t", role="tutor")
        student = User.objects.create(username="s", role="student")
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)
        task = Task.objects.create(topic=topic, task_type=task_type, fipi_id="1", correct_answer="2", difficulty=10, exam_points=1)
        assignment = Assignment.objects.create(tutor=tutor, student=student, title="Вариант 1")
        assignment.tasks.add(task)

        self.client.force_login(student)
        url = reverse("student_check_assignment_task", args=[assignment.id, task.id])
        res = self.client.post(url, {"answer": "2"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("comments_count", data)
        self.assertIn("can_view_comments", data)
```

- [ ] **Step 2: Run the test to confirm failure**

Run:
```bash
python manage.py test core.tests.test_submission_comments.SubmissionCheckCommentsResponseTests -v 1
```

Expected: FAIL (missing keys).

- [ ] **Step 3: Implement JSON additions in `student_check_assignment_task`**

In `core/views.py` update response to include:

```python
return JsonResponse({
    "is_correct": is_correct,
    "correct_answer": task.correct_answer,
    "solution_html": solution_html,
    "xp_gained": xp_gained if is_correct and created else 0,
    "comments_count": submission.comments.count(),
    "can_view_comments": submission.is_correct is not None,
    "submission_id": submission.id,
})
```

- [ ] **Step 4: Ensure `student_solve_assignment` prefetches comments**

Change the GET query in `student_solve_assignment`:

```python
saved_submissions = {
    sub.task_id: sub
    for sub in Submission.objects.filter(assignment=assignment, student=request.user)
    .select_related("assignment")
    .prefetch_related("comments", "comments__author")
}
```

- [ ] **Step 5: Add UI to `student_solve_assignment.html`**

For each task card, add:

- textarea:
  - `id="comment_text_{{ task.id }}"`
- send button:
  - `onclick="postComment({{ assignment.id }}, {{ task.id }})"`
- a hidden thread block:
  - `id="comments_wrap_{{ task.id }}"` (initially `hidden` unless `task.saved_submission.is_correct is not None`)

Client JS (append below existing script):

```html
<script>
  async function postComment(assignmentId, taskId) {
    const input = document.getElementById(`comment_text_${taskId}`);
    const text = (input?.value || "").trim();
    if (!text) return;

    const formData = new FormData();
    formData.append("text", text);
    formData.append("csrfmiddlewaretoken", "{{ csrf_token }}");

    const res = await fetch(`/student/assignment/${assignmentId}/task/${taskId}/comment/`, { method: "POST", body: formData });
    if (!res.ok) {
      alert("Не удалось отправить сообщение");
      return;
    }
    input.value = "";
  }
</script>
```

Then, in `checkTask()` success branch after `data` is parsed, if `data.can_view_comments` is true:
- unhide `comments_wrap_<taskId>`
- optionally show a “Вопросы (N)” label using `data.comments_count`

- [ ] **Step 6: Run tests**

Run:
```bash
python manage.py test core.tests.test_submission_comments.SubmissionCheckCommentsResponseTests -v 1
python manage.py test core.tests.test_submission_comments -v 1
```

Expected: PASS.

---

### Task 4: Display threads in student history

**Files:**
- Modify: `core/views.py` (`student_history`)
- Modify: `core/templates/core/student_history.html`
- Test: `core/tests/test_submission_comments.py`

- [ ] **Step 1: Prefetch comments in `student_history`**

In `student_history` view:

```python
submissions = (
    Submission.objects.filter(student=request.user)
    .select_related("task", "assignment")
    .prefetch_related("comments", "comments__author")
    .order_by("-created_at")
)
```

- [ ] **Step 2: Render thread in `student_history.html`**

Under each submission item, add:
- button “Вопросы ({{ sub.comments.count }})” (only if count > 0)
- hidden div with message list (author role + time + text)

- [ ] **Step 3: Add a minimal render test (optional)**

If you want a template-level safety net:
- create a submission + 1 comment and assert response contains comment text.

---

### Task 5: Tutor replies in tutor history

**Files:**
- Modify: `core/views.py` (`tutor_student_history`)
- Modify: `core/templates/core/tutor_student_history.html`
- Test: `core/tests/test_submission_comments.py`

- [ ] **Step 1: Prefetch comments in `tutor_student_history` context**

Where tutor history builds `assign_data.submissions` / `practice.submissions`, make sure those QuerySets use:

```python
.prefetch_related("comments", "comments__author")
```

- [ ] **Step 2: Add message list + reply form**

In the detailed block `task_{{ sub.id }}` and `prac_task_{{ sub.id }}`, add:
- message list
- textarea `id="tutor_comment_text_{{ sub.id }}"`
- button `onclick="tutorPostComment({{ sub.id }})"`

JS:

```html
<script>
  async function tutorPostComment(submissionId) {
    const input = document.getElementById(`tutor_comment_text_${submissionId}`);
    const text = (input?.value || "").trim();
    if (!text) return;

    const formData = new FormData();
    formData.append("text", text);
    formData.append("csrfmiddlewaretoken", "{{ csrf_token }}");

    const res = await fetch(`/tutor/submission/${submissionId}/comment/`, { method: "POST", body: formData });
    if (!res.ok) {
      alert("Не удалось отправить ответ");
      return;
    }
    input.value = "";
    location.reload();
  }
</script>
```

- [ ] **Step 3: Run tutor permission tests**

Run:
```bash
python manage.py test core.tests.test_submission_comments.SubmissionCommentEndpointTests -v 1
```

Expected: PASS.

---

### Task 6: Tutor replies in assignment view page

**Files:**
- Create: `core/templates/core/tutor_assignment_view.html`
- Modify: `core/views.py` (new `tutor_assignment_view`)
- Modify: `core/urls.py` (route to the new view)
- Test: `core/tests/test_submission_comments.py`

- [ ] **Step 1: Add failing test for tutor assignment view access**

Add:

```python
class TutorAssignmentViewAccessTests(TestCase):
    def test_tutor_can_open_own_assignment_view(self):
        tutor = User.objects.create(username="t", role="tutor")
        student = User.objects.create(username="s", role="student")
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)
        task = Task.objects.create(topic=topic, task_type=task_type, fipi_id="1", correct_answer="1", difficulty=10, exam_points=1)
        assignment = Assignment.objects.create(tutor=tutor, student=student, title="Вариант 1", is_draft=False)
        assignment.tasks.add(task)

        self.client.force_login(tutor)
        url = reverse("tutor_assignment_view", args=[assignment.id])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertIn("Вариант 1", res.content.decode("utf-8"))
```

- [ ] **Step 2: Add URL + view**

In `core/urls.py` add:

```python
path("tutor/assignment/<int:assignment_id>/", views.tutor_assignment_view, name="tutor_assignment_view"),
```

In `core/views.py` add:

```python
@login_required
def tutor_assignment_view(request, assignment_id):
    if request.user.role != "tutor":
        return redirect("login")

    assignment = get_object_or_404(Assignment, id=assignment_id, tutor=request.user)
    tasks = list(assignment.tasks.all())

    subs = (
        Submission.objects.filter(assignment=assignment, task_id__in=[t.id for t in tasks])
        .select_related("student", "task")
        .prefetch_related("comments", "comments__author")
    )
    subs_by_task = {s.task_id: s for s in subs}

    for t in tasks:
        t.submission = subs_by_task.get(t.id)

    return render(request, "core/tutor_assignment_view.html", {"assignment": assignment, "tasks": tasks})
```

- [ ] **Step 3: Create template**

Create `core/templates/core/tutor_assignment_view.html` based on the style of `tutor_preview_assignment.html` but without draft actions. For each task:
- show condition
- show student answer (if `task.submission`)
- show comments list + reply textarea using `tutorPostComment(submission_id)`

- [ ] **Step 4: Run the access test**

Run:
```bash
python manage.py test core.tests.test_submission_comments.TutorAssignmentViewAccessTests -v 1
```

Expected: PASS.

---

### Task 7: Full suite, smoke-check, commit & push

**Files:**
- All modified/created above

- [ ] **Step 1: Run full test suite**

Run:
```bash
python manage.py test core.tests -v 1
```

Expected: PASS.

- [ ] **Step 2: Manual smoke checklist**

- Student solve page:
  - can submit question before check (no thread shown yet)
  - after pressing “Проверить”, thread becomes visible and includes prior messages
- Student history:
  - shows thread for the submission
- Tutor student history:
  - shows thread and allows reply
- Tutor assignment view:
  - shows tasks + threads, allows reply

- [ ] **Step 3: Commit and push**

```bash
git add core/models.py core/migrations core/views.py core/urls.py core/templates/core/student_solve_assignment.html core/templates/core/student_history.html core/templates/core/tutor_student_history.html core/templates/core/tutor_assignment_view.html core/tests/test_submission_comments.py
git commit -m "feat: add per-submission comment threads for student and tutor"
git push origin main
```

