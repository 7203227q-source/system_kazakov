# Unread Badges for Submission Comments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add “unread” signaling for task comment threads: tutors see new student questions, students see new tutor replies, with clickable badges/links.

**Architecture:** Extend `SubmissionComment` with `seen_by_tutor_at` and `seen_by_student_at`. When a message is created, it’s considered read for the author role and unread for the other role. When tutor/student opens relevant pages, mark eligible messages as seen. Add counters in dashboards/sidebars and per-assignment/per-student badges.

**Tech Stack:** Django ORM, existing templates (`tutor_dashboard`, `student_dashboard`, sidebars), existing views.

---

## File Map

**Modify**
- `core/models.py` (add seen fields)
- `core/migrations/0034_submissioncomment_seen_fields.py` (new migration)
- `core/views.py` (mark-as-seen logic + counters in dashboards)
- `core/templates/core/tutor_dashboard.html` (badges per student)
- `core/templates/core/student_dashboard.html` (badges per assignment)
- `core/templates/core/includes/_student_sidebar.html` (badge on journal link)
- `core/templates/core/includes/_tutor_sidebar.html` (optional global badge)
- `core/templates/core/student_history.html` (mark tutor replies seen)
- `core/templates/core/student_solve_assignment.html` (mark tutor replies seen when visible)
- `core/templates/core/tutor_student_history.html` (mark student questions seen)
- `core/templates/core/tutor_assignment_view.html` (mark student questions seen + per-task badge)
- `core/tests/test_submission_comment_unread.py` (new tests)

---

### Task 1: Add “seen” fields to `SubmissionComment`

**Files:**
- Modify: `core/models.py`
- Create: `core/migrations/0034_submissioncomment_seen_fields.py`
- Test: `core/tests/test_submission_comment_unread.py`

- [ ] **Step 1: Write failing test for seen defaults**

Create `core/tests/test_submission_comment_unread.py`:

```python
from django.test import TestCase

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, Submission, User


class SubmissionCommentUnreadTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create(username="t", role="tutor")
        self.student = User.objects.create(username="s", role="student")
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=False)
        topic = Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)
        self.task = Task.objects.create(topic=topic, task_type=task_type, fipi_id="1", correct_answer="1", difficulty=10, exam_points=1)
        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="Вариант 1")
        self.assignment.tasks.add(self.task)
        self.sub = Submission.objects.create(student=self.student, task=self.task, assignment=self.assignment, user_answer="", is_correct=None)

    def test_student_message_is_unseen_for_tutor(self):
        c = self.sub.comments.create(author=self.student, author_role="student", text="q")
        self.assertIsNotNone(c.seen_by_student_at)
        self.assertIsNone(c.seen_by_tutor_at)
```

- [ ] **Step 2: Run test to confirm it fails**

Run:
```bash
python manage.py test core.tests.test_submission_comment_unread -v 1
```

Expected: FAIL (fields missing).

- [ ] **Step 3: Add fields to model**

In `core/models.py` in `SubmissionComment`:

```python
seen_by_tutor_at = models.DateTimeField(null=True, blank=True)
seen_by_student_at = models.DateTimeField(null=True, blank=True)
```

- [ ] **Step 4: Create migration**

Run:
```bash
python manage.py makemigrations core
```

- [ ] **Step 5: Make creation endpoints set seen fields**

Student endpoint: set `seen_by_student_at=timezone.now()`, tutor seen null.
Tutor endpoint: set `seen_by_tutor_at=timezone.now()`, student seen null.

- [ ] **Step 6: Run test**

Run:
```bash
python manage.py test core.tests.test_submission_comment_unread -v 1
```

Expected: PASS.

---

### Task 2: Mark messages as seen on page views

**Files:**
- Modify: `core/views.py`
- Test: `core/tests/test_submission_comment_unread.py`

- [ ] **Step 1: Implement helpers**

In `core/views.py` add helpers:

```python
def _mark_student_replies_seen(student: User, submissions_qs):
    from django.utils import timezone
    now = timezone.now()
    SubmissionComment.objects.filter(
        submission__in=submissions_qs,
        author_role="tutor",
        seen_by_student_at__isnull=True,
    ).update(seen_by_student_at=now)


def _mark_tutor_questions_seen(tutor: User, submissions_qs):
    from django.utils import timezone
    now = timezone.now()
    SubmissionComment.objects.filter(
        submission__in=submissions_qs,
        author_role="student",
        seen_by_tutor_at__isnull=True,
        submission__assignment__tutor=tutor,
    ).update(seen_by_tutor_at=now)
```

- [ ] **Step 2: Wire into views**

Student:
- `student_history`: mark all unseen tutor messages for that student as seen.
- `student_solve_assignment`: mark tutor messages seen only for submissions where `is_correct is not None` (thread visible).

Tutor:
- `tutor_student_history`: mark all unseen student messages for that tutor+student as seen.
- `tutor_assignment_view`: mark unseen student messages for that assignment as seen.

- [ ] **Step 3: Add tests for mark-as-seen**

Add tests that:
- create tutor message (unseen by student) → hitting `student_history` marks it seen.
- create student message (unseen by tutor) → hitting `tutor_student_history` marks it seen.

---

### Task 3: Compute unread counters and show badges/links

**Files:**
- Modify: `core/views.py`
- Modify templates listed in File Map

- [ ] **Step 1: Tutor dashboard student list badge**

In `tutor_dashboard` view, for each student compute:

```python
s.unread_student_questions = SubmissionComment.objects.filter(
    submission__student=s,
    submission__assignment__tutor=request.user,
    author_role="student",
    seen_by_tutor_at__isnull=True,
).count()
```

In `tutor_dashboard.html` near student name add a badge if `> 0`:
- text “Вопросы: N”
- link to `tutor_student_history` for that student.

- [ ] **Step 2: Student sidebar badge**

In `student_dashboard` and `student_history` views add `unread_tutor_replies_total`:

```python
unread_tutor_replies_total = SubmissionComment.objects.filter(
    submission__student=request.user,
    author_role="tutor",
    seen_by_student_at__isnull=True,
).count()
```

Update `_student_sidebar.html`:
- show badge on “Журнал решений” if `unread_tutor_replies_total > 0`

- [ ] **Step 3: Student dashboard badge per assignment**

In `student_dashboard` build a map `assignment_id -> unread_count` for `pending_assignments`:

```python
unread_by_assignment = {
    row["submission__assignment_id"]: row["c"]
    for row in SubmissionComment.objects.filter(
        submission__student=request.user,
        author_role="tutor",
        seen_by_student_at__isnull=True,
        submission__assignment_id__in=pending_assignments.values_list("id", flat=True),
    ).values("submission__assignment_id").annotate(c=models.Count("id"))
}
```

Then in template show badge “Ответы: N” and link to `student_solve_assignment`.

- [ ] **Step 4: Tutor assignment view per-task badge**

Compute per submission:
`unread_student_questions = count(student comments with seen_by_tutor_at is null)` and show badge in task header.

---

### Task 4: Run full suite, commit, push

- [ ] Run:
```bash
python manage.py test core.tests -v 1
```

- [ ] Commit:
```bash
git add core/models.py core/migrations core/views.py core/templates/core core/tests/test_submission_comment_unread.py
git commit -m "feat: add unread badges for submission comments"
git push origin main
```

