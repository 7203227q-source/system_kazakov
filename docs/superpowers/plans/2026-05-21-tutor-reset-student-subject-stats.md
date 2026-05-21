# Tutor Reset Student Subject Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tutor-only action to fully reset a student’s stats for a specific subject, with a confirmation modal and irreversible warning.

**Architecture:** Add a new POST endpoint guarded by tutor→student permissions. On confirmation, run an atomic reset that: (1) resets StudentSubjectProfile analytics+XP, (2) deletes analytics rows/logs/submissions/SRS for tasks in that subject, (3) soft-deletes subject assignments. Add a UI button on tutor dashboard with a modal + checkbox gate.

**Tech Stack:** Django views/urls/templates, Django ORM + `transaction.atomic`, Django messages, existing Tailwind UI patterns, Django tests.

---

## File Map

**Modify**
- [core/views.py](file:///workspace/core/views.py): add POST view `tutor_reset_student_subject_stats`.
- [core/urls.py](file:///workspace/core/urls.py): add route for the endpoint.
- [core/templates/core/tutor_dashboard.html](file:///workspace/core/templates/core/tutor_dashboard.html): add “Сбросить статистику” button + modal + checkbox confirmation.

**Create**
- `core/tests/test_tutor_reset_student_subject_stats.py`: TDD coverage for permissions and reset behavior.

---

## Behavior Definition (Max Reset)

Given tutor T, student S (linked to T), and subject X:

1) **StudentSubjectProfile(S,X)**:
   - keep: `target_score`, `exam_format`, `exam_date`
   - reset:
     - `xp=0`, `level=1`, `current_streak=0`
     - `avg_model_error=0.0`, `trust_factor=0.6`, `learning_velocity=1.0`
     - `last_verified_date=None`, `last_streak_date=None`

2) **Delete data (hard delete) scoped to subject tasks**:
   - `DailySnapshot(student=S, subject=X)` rows
   - `TaskLog(student=S, task__topic__subject=X)`
   - `SpacedRepetition(student=S, task__topic__subject=X)`
   - `Submission(student=S, task__topic__subject=X)` (comments cascade)

3) **Assignments (soft-delete)**:
   - Select assignments of student S that belong to subject X:
     - safe rule: **all tasks in assignment are from subject X**
       - include assignment if `assignment.tasks.count() == assignment.tasks.filter(topic__subject=X).count()`
   - Set:
     - `is_deleted=True`, `deleted_at=timezone.now()`, `deleted_by=request.user`

4) **Confirmation gating**:
   - UI: modal + checkbox “Я понимаю, что действие необратимо” required to enable confirm.
   - Backend: require POST param `confirm=1` (or `confirmed=1`) else 400.

---

## Task 1: Write failing tests (TDD)

**Files:**
- Create: [test_tutor_reset_student_subject_stats.py](file:///workspace/core/tests/test_tutor_reset_student_subject_stats.py)

- [ ] **Step 1: Test happy path resets everything**

Create:
- tutor, student, tutor.students.add(student)
- subject X + exam format + topic + two tasks in subject X
- StudentSubjectProfile for (student, X) with non-default values
- DailySnapshot rows for (student, X)
- Submission rows for student on those tasks (one with assignment, one practice)
- TaskLog rows for those tasks
- SpacedRepetition rows for those tasks
- Assignment A that contains only subject X tasks (should be soft-deleted)
- Assignment B that mixes subjects (should remain untouched) OR assignment with other subject tasks (best: create subject Y + taskY, add to B)

Call POST endpoint with `confirm=1`.

Assert:
- profile reset fields exactly
- snapshots/logs/srs/submissions for subject X are deleted
- assignment A set `is_deleted=True` and `deleted_by=tutor`
- assignment B not deleted
- response is redirect back to dashboard (302)

Skeleton:

```python
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Assignment, DailySnapshot, ExamFormat, SpacedRepetition, StudentSubjectProfile,
    Subject, Submission, Task, TaskLog, TaskType, Topic, User,
)

class TutorResetStudentSubjectStatsTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor.students.add(self.student)

        self.subj_x = Subject.objects.create(name="Математика")
        self.ef_x = ExamFormat.objects.create(subject=self.subj_x, name="ЕГЭ", year=2026, is_active=True)
        self.topic_x = Topic.objects.create(subject=self.subj_x, name="T")
        self.tt_x = TaskType.objects.create(exam_format=self.ef_x, number=1, name="1", max_points=1)
        self.task_x1 = Task.objects.create(topic=self.topic_x, task_type=self.tt_x, correct_answer="1", difficulty=10, exam_points=1)
        self.task_x2 = Task.objects.create(topic=self.topic_x, task_type=self.tt_x, correct_answer="1", difficulty=10, exam_points=1)

        self.subj_y = Subject.objects.create(name="Физика")
        self.ef_y = ExamFormat.objects.create(subject=self.subj_y, name="ЕГЭ физика", year=2026, is_active=True)
        self.topic_y = Topic.objects.create(subject=self.subj_y, name="TY")
        self.tt_y = TaskType.objects.create(exam_format=self.ef_y, number=1, name="1", max_points=1)
        self.task_y = Task.objects.create(topic=self.topic_y, task_type=self.tt_y, correct_answer="1", difficulty=10, exam_points=1)

    def test_reset_maximum(self):
        p = StudentSubjectProfile.objects.create(
            student=self.student, subject=self.subj_x, exam_format=self.ef_x,
            target_score=80, xp=250, level=3, current_streak=7,
            avg_model_error=1.5, trust_factor=0.2, learning_velocity=0.3,
        )
        DailySnapshot.objects.create(student=self.student, subject=self.subj_x, current_mastery=55.0, predicted_exam_score=60.0)
        TaskLog.objects.create(student=self.student, task=self.task_x1, score=1)
        TaskLog.objects.create(student=self.student, task=self.task_y, score=1)
        SpacedRepetition.objects.create(student=self.student, task=self.task_x1)
        SpacedRepetition.objects.create(student=self.student, task=self.task_y)
        Submission.objects.create(student=self.student, task=self.task_x1, user_answer="1", is_correct=True, score=1)
        Submission.objects.create(student=self.student, task=self.task_y, user_answer="1", is_correct=True, score=1)

        a_only_x = Assignment.objects.create(tutor=self.tutor, student=self.student, title="AX", is_draft=False, is_completed=False, exam_format=self.ef_x)
        a_only_x.tasks.add(self.task_x1, self.task_x2)
        a_mixed = Assignment.objects.create(tutor=self.tutor, student=self.student, title="AM", is_draft=False, is_completed=False, exam_format=self.ef_x)
        a_mixed.tasks.add(self.task_x1, self.task_y)

        self.client.login(username="t", password="pass")
        url = reverse("tutor_reset_student_subject_stats", args=[self.student.id, self.subj_x.id])
        res = self.client.post(url, data={"confirm": "1"})
        self.assertEqual(res.status_code, 302)

        p.refresh_from_db()
        self.assertEqual(p.xp, 0)
        self.assertEqual(p.level, 1)
        self.assertEqual(p.current_streak, 0)
        self.assertEqual(p.trust_factor, 0.6)
        self.assertEqual(p.learning_velocity, 1.0)
        self.assertEqual(p.avg_model_error, 0.0)
        self.assertIsNone(p.last_verified_date)
        self.assertIsNone(p.last_streak_date)
        self.assertEqual(p.target_score, 80)
        self.assertEqual(p.exam_format_id, self.ef_x.id)

        self.assertEqual(DailySnapshot.objects.filter(student=self.student, subject=self.subj_x).count(), 0)
        self.assertEqual(TaskLog.objects.filter(student=self.student, task__topic__subject=self.subj_x).count(), 0)
        self.assertEqual(SpacedRepetition.objects.filter(student=self.student, task__topic__subject=self.subj_x).count(), 0)
        self.assertEqual(Submission.objects.filter(student=self.student, task__topic__subject=self.subj_x).count(), 0)

        a_only_x.refresh_from_db()
        self.assertTrue(a_only_x.is_deleted)
        self.assertEqual(a_only_x.deleted_by_id, self.tutor.id)
        self.assertIsNotNone(a_only_x.deleted_at)

        a_mixed.refresh_from_db()
        self.assertFalse(a_mixed.is_deleted)
```

- [ ] **Step 2: Test permissions**

Cases:
- non-tutor user gets 403
- tutor not linked to student gets 403
- missing confirm param returns 400

Add three tests in same file.

- [ ] **Step 3: Run tests and watch them fail**

Run:
```bash
python manage.py test core.tests.test_tutor_reset_student_subject_stats -v 2
```
Expected: FAIL because url/view doesn’t exist yet.

---

## Task 2: Implement endpoint + URL

**Files:**
- Modify: [urls.py](file:///workspace/core/urls.py)
- Modify: [views.py](file:///workspace/core/views.py)

- [ ] **Step 1: Add URL pattern**

In `core/urls.py` add:

```python
path(
    "tutor/student/<int:student_id>/subject/<int:subject_id>/reset/",
    views.tutor_reset_student_subject_stats,
    name="tutor_reset_student_subject_stats",
)
```

- [ ] **Step 2: Add view implementation**

In `core/views.py` create a `@login_required @require_POST` view near tutor endpoints:

Implementation outline:

```python
from django.db import transaction
from django.utils import timezone

@login_required
@require_POST
def tutor_reset_student_subject_stats(request, student_id, subject_id):
    if request.user.role != "tutor":
        return JsonResponse({"error": "forbidden"}, status=403)
    if not request.user.students.filter(id=student_id).exists():
        return JsonResponse({"error": "forbidden"}, status=403)
    if (request.POST.get("confirm") or "").strip() != "1":
        return JsonResponse({"error": "confirm_required"}, status=400)

    student = User.objects.filter(id=student_id, role="student").first()
    subject = Subject.objects.filter(id=subject_id).first()
    if student is None or subject is None:
        return JsonResponse({"error": "not_found"}, status=404)

    now = timezone.now()
    with transaction.atomic():
        profile = StudentSubjectProfile.objects.filter(student=student, subject=subject).first()
        if profile:
            profile.xp = 0
            profile.level = 1
            profile.current_streak = 0
            profile.avg_model_error = 0.0
            profile.trust_factor = 0.6
            profile.learning_velocity = 1.0
            profile.last_verified_date = None
            profile.last_streak_date = None
            profile.save(update_fields=[
                "xp","level","current_streak","avg_model_error","trust_factor",
                "learning_velocity","last_verified_date","last_streak_date",
            ])

        DailySnapshot.objects.filter(student=student, subject=subject).delete()
        TaskLog.objects.filter(student=student, task__topic__subject=subject).delete()
        SpacedRepetition.objects.filter(student=student, task__topic__subject=subject).delete()
        Submission.objects.filter(student=student, task__topic__subject=subject).delete()

        candidate = Assignment.objects.filter(student=student, is_deleted=False)
        # keep only assignments where all tasks belong to subject
        ids = []
        for a in candidate:
            total = a.tasks.count()
            if total and total == a.tasks.filter(topic__subject=subject).count():
                ids.append(a.id)
        Assignment.objects.filter(id__in=ids).update(
            is_deleted=True,
            deleted_at=now,
            deleted_by=request.user,
        )

    messages.success(request, f"Статистика по предмету «{subject.name}» сброшена.")
    return redirect(f\"{reverse('tutor_dashboard')}?student_id={student.id}&subject_id={subject.id}\")
```

Notes:
- Don’t delete `Subject`, `Task`, `TaskVariant` etc.
- Keep assignment soft-delete (set deleted fields).

- [ ] **Step 3: Run tests**

```bash
python manage.py test core.tests.test_tutor_reset_student_subject_stats -v 2
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add core/urls.py core/views.py core/tests/test_tutor_reset_student_subject_stats.py
git commit -m "feat: allow tutor to reset student subject stats"
```

---

## Task 3: Add UI button + modal + checkbox confirmation

**Files:**
- Modify: [tutor_dashboard.html](file:///workspace/core/templates/core/tutor_dashboard.html)
- Test: reuse existing view tests if any, otherwise add a small template presence test (optional)

- [ ] **Step 1: Add “Сбросить статистику” action near subject selector**

Add a button that opens modal; only show when:
- `selected_student` exists
- `chart_subject_id` is set (a subject selected)

Button:
- style consistent with other header actions
- text: “Сбросить статистику”
- onClick: open modal

- [ ] **Step 2: Modal markup**

Create a hidden modal div (similar style to existing modals in codebase if present):
- Title: “Сбросить статистику по предмету”
- Body: bullet list of what will be deleted (submissions, SRS, analytics, and assignments will be hidden)
- Checkbox required: `id="reset_confirm_checkbox"`
- Confirm button disabled until checked
- Form posts to `tutor_reset_student_subject_stats` with `confirm=1` and CSRF.

Example JS inline:
- toggle modal visibility
- on checkbox change: enable/disable submit button

- [ ] **Step 3: Run minimal regression tests**

```bash
python manage.py test core.tests.test_tutor_reset_student_subject_stats -v 2
```

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/tutor_dashboard.html
git commit -m "feat: add tutor UI for subject stats reset"
```

---

## Self-Review Checklist

- [ ] Only tutor with access to student can reset (403 otherwise)
- [ ] Backend requires confirm=1 even if UI bypassed
- [ ] Uses `transaction.atomic()`
- [ ] Assignments are soft-deleted, not hard-deleted
- [ ] Deletes are scoped to subject tasks only
- [ ] Tests cover happy path + permissions + confirm gate

