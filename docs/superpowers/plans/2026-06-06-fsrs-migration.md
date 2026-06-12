# FSRS Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current SM-2 spaced repetition scheduler with FSRS while keeping the student UI binary (`верно / неверно`), preserving the existing due queue, and using active solve time plus attempt count as hidden review signals.

**Architecture:** Keep `next_review_date` as the single source of truth for due-queue selection, but move scheduling logic behind a new `core/fsrs_engine.py` adapter. Extend `SpacedRepetition` with `fsrs_state` and `srs_algorithm`, collect real `active_time_seconds` in `student_practice`, map each review to `Again / Hard / Good`, and migrate legacy SM-2 rows lazily on their next review.

**Tech Stack:** Django 6, Python 3.11+, PostgreSQL/SQLite via Django ORM, `fsrs==6.3.1`, Django TestCase, existing `core` templates/views/services.

---

## File Structure

- Create: `core/fsrs_engine.py`
- Create: `core/migrations/0061_spacedrepetition_fsrs_fields.py`
- Create: `core/tests/test_fsrs_review_signal.py`
- Create: `core/tests/test_fsrs_soft_migration.py`
- Create: `core/tests/test_student_practice_srs_active_time.py`
- Modify: `requirements.txt`
- Modify: `core/models.py`
- Modify: `core/services.py`
- Modify: `core/views.py`
- Modify: `core/templates/core/student_practice.html`
- Modify: `core/tests/test_tutor_dashboard_srs_counters.py`
- Modify: `core/tests/test_student_practice_srs_mode_persists.py`
- Modify: `core/tests/test_practice_answer_lock.py`

### Task 1: Add FSRS Model Fields And Engine Wrapper

**Files:**
- Create: `core/fsrs_engine.py`
- Create: `core/migrations/0061_spacedrepetition_fsrs_fields.py`
- Modify: `requirements.txt`
- Modify: `core/models.py`
- Test: `core/tests/test_fsrs_soft_migration.py`

- [ ] **Step 1: Write the failing test for new and legacy SRS rows**

```python
from django.test import TestCase
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, Subject, Task, TaskType, Topic, User
from core.services import process_task_submission


class FSRSSoftMigrationTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="fsrs_s", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тест", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="42", difficulty=40, exam_points=1)

    def test_new_record_is_created_as_fsrs(self):
        rec = process_task_submission(
            self.student,
            self.task,
            grade=5,
            active_time_seconds=35,
            attempt_count=1,
        )
        self.assertEqual(rec.srs_algorithm, "fsrs")
        self.assertIsInstance(rec.fsrs_state, dict)
        self.assertTrue(rec.fsrs_state)
        self.assertGreaterEqual(rec.next_review_date, timezone.localdate())

    def test_legacy_sm2_record_is_soft_migrated_on_next_review(self):
        legacy = SpacedRepetition.objects.create(
            student=self.student,
            task=self.task,
            easiness_factor=2.5,
            interval=6,
            repetitions=2,
            next_review_date=timezone.localdate(),
        )
        self.assertFalse(bool(getattr(legacy, "fsrs_state", None)))
        self.assertEqual(getattr(legacy, "srs_algorithm", "sm2"), "sm2")

        rec = process_task_submission(
            self.student,
            self.task,
            grade=1,
            active_time_seconds=75,
            attempt_count=2,
        )
        self.assertEqual(rec.id, legacy.id)
        self.assertEqual(rec.srs_algorithm, "fsrs")
        self.assertIsInstance(rec.fsrs_state, dict)
        self.assertTrue(rec.fsrs_state)
```

- [ ] **Step 2: Run the focused test to confirm the fields and new signature are missing**

Run: `python manage.py test core.tests.test_fsrs_soft_migration -v 2`

Expected: FAIL with errors like `TypeError: process_task_submission() got an unexpected keyword argument 'active_time_seconds'` and/or `AttributeError: 'SpacedRepetition' object has no attribute 'srs_algorithm'`.

- [ ] **Step 3: Add the dependency and model fields**

```python
# requirements.txt
fsrs==6.3.1
```

```python
# core/models.py
class SpacedRepetition(models.Model):
    SRS_ALGORITHM_CHOICES = [
        ("sm2", "SM-2"),
        ("fsrs", "FSRS"),
    ]

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='srs_progress', limit_choices_to={'role': 'student'})
    task = models.ForeignKey(Task, on_delete=models.CASCADE)

    easiness_factor = models.FloatField(default=2.5, verbose_name="E-Factor")
    interval = models.IntegerField(default=0, verbose_name="Интервал (в днях)")
    repetitions = models.IntegerField(default=0, verbose_name="Успешных повторений подряд")
    next_review_date = models.DateField(default=timezone.now, verbose_name="Дата следующего повторения")

    srs_algorithm = models.CharField(
        max_length=10,
        choices=SRS_ALGORITHM_CHOICES,
        default="sm2",
        db_index=True,
        verbose_name="Алгоритм интервального повторения",
    )
    fsrs_state = models.JSONField(default=dict, blank=True, verbose_name="FSRS state")

    last_grade = models.IntegerField(null=True, blank=True, verbose_name="Последняя оценка (0-5)")
    last_reviewed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_suspended = models.BooleanField(default=False, db_index=True)
```

```python
# core/migrations/0061_spacedrepetition_fsrs_fields.py
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0060_srs_suspension_and_removal_requests"),
    ]

    operations = [
        migrations.AddField(
            model_name="spacedrepetition",
            name="srs_algorithm",
            field=models.CharField(
                choices=[("sm2", "SM-2"), ("fsrs", "FSRS")],
                db_index=True,
                default="sm2",
                max_length=10,
                verbose_name="Алгоритм интервального повторения",
            ),
        ),
        migrations.AddField(
            model_name="spacedrepetition",
            name="fsrs_state",
            field=models.JSONField(blank=True, default=dict, verbose_name="FSRS state"),
        ),
    ]
```

- [ ] **Step 4: Add the FSRS adapter wrapper**

```python
# core/fsrs_engine.py
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Any

from fsrs import Card, Rating, Scheduler


SCHEDULER = Scheduler(enable_fuzzing=False)


def load_card(fsrs_state: dict[str, Any] | None) -> Card:
    if fsrs_state:
        return Card.from_dict(fsrs_state)
    return Card()


def rating_from_label(label: str) -> Rating:
    mapping = {
        "again": Rating.Again,
        "hard": Rating.Hard,
        "good": Rating.Good,
    }
    return mapping[label]


def review_card(fsrs_state: dict[str, Any] | None, label: str) -> dict[str, Any]:
    card = load_card(fsrs_state)
    reviewed_card, _review_log = SCHEDULER.review_card(
        card=card,
        rating=rating_from_label(label),
        review_datetime=datetime.now(dt_timezone.utc),
    )
    return reviewed_card.to_dict()
```

- [ ] **Step 5: Extend `process_task_submission()` just enough to create/update FSRS rows**

```python
# core/services.py
def process_task_submission(student, task, grade, *, active_time_seconds=None, attempt_count=1):
    srs_record, _created = SpacedRepetition.objects.get_or_create(
        student=student,
        task=task,
        defaults={
            "easiness_factor": 2.5,
            "interval": 0,
            "repetitions": 0,
            "next_review_date": timezone.now().date(),
            "srs_algorithm": "fsrs",
            "fsrs_state": {},
        },
    )
    return process_srs_review(
        srs_record,
        grade,
        active_time_seconds=active_time_seconds,
        attempt_count=attempt_count,
    )
```

- [ ] **Step 6: Run migrations and the focused test**

Run: `python manage.py test core.tests.test_fsrs_soft_migration -v 2`

Expected: PASS for both tests in `FSRSSoftMigrationTests`.

- [ ] **Step 7: Commit the model and wrapper scaffold**

```bash
git add requirements.txt core/models.py core/services.py core/fsrs_engine.py core/migrations/0061_spacedrepetition_fsrs_fields.py core/tests/test_fsrs_soft_migration.py
git commit -m "feat: add fsrs state scaffold"
```

### Task 2: Implement Review Signal Mapping

**Files:**
- Create: `core/tests/test_fsrs_review_signal.py`
- Modify: `core/fsrs_engine.py`
- Modify: `core/services.py`

- [ ] **Step 1: Write the failing tests for `Again / Hard / Good` mapping**

```python
from django.test import SimpleTestCase

from core.services import determine_fsrs_signal


class FSRSReviewSignalTests(SimpleTestCase):
    def test_wrong_answer_maps_to_again(self):
        signal = determine_fsrs_signal(
            is_correct=False,
            active_time_seconds=20,
            attempt_count=1,
            expected_time_seconds=60,
        )
        self.assertEqual(signal, "again")

    def test_correct_answer_after_multiple_attempts_maps_to_hard(self):
        signal = determine_fsrs_signal(
            is_correct=True,
            active_time_seconds=40,
            attempt_count=2,
            expected_time_seconds=60,
        )
        self.assertEqual(signal, "hard")

    def test_correct_but_slow_answer_maps_to_hard(self):
        signal = determine_fsrs_signal(
            is_correct=True,
            active_time_seconds=140,
            attempt_count=1,
            expected_time_seconds=60,
        )
        self.assertEqual(signal, "hard")

    def test_correct_normal_speed_first_attempt_maps_to_good(self):
        signal = determine_fsrs_signal(
            is_correct=True,
            active_time_seconds=55,
            attempt_count=1,
            expected_time_seconds=60,
        )
        self.assertEqual(signal, "good")
```

- [ ] **Step 2: Run the new tests to confirm the helper does not exist**

Run: `python manage.py test core.tests.test_fsrs_review_signal -v 2`

Expected: FAIL with `ImportError` or `AttributeError` for `determine_fsrs_signal`.

- [ ] **Step 3: Add time normalization and signal helpers**

```python
# core/services.py
def normalize_active_time_seconds(value):
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return min(seconds, 60 * 60)


def get_expected_time_seconds(student):
    avg = (
        TaskLog.objects.filter(student=student, is_anomaly=False, time_spent__gt=0)
        .aggregate(a=models.Avg("time_spent"))
        .get("a")
    )
    if not avg:
        avg = (
            TaskLog.objects.filter(is_anomaly=False, time_spent__gt=0)
            .aggregate(a=models.Avg("time_spent"))
            .get("a")
        )
    return int(avg or 60)


def determine_fsrs_signal(*, is_correct, active_time_seconds, attempt_count, expected_time_seconds):
    if not is_correct:
        return "again"
    if int(attempt_count or 1) > 1:
        return "hard"
    if active_time_seconds is None:
        return "good"
    relative_time = float(active_time_seconds) / float(max(expected_time_seconds, 1))
    if relative_time >= 1.75:
        return "hard"
    return "good"
```

- [ ] **Step 4: Update `process_srs_review()` to consume the signal**

```python
# core/services.py
from datetime import datetime

from .fsrs_engine import review_card


def process_srs_review(srs_record, grade, *, active_time_seconds=None, attempt_count=1):
    is_correct = int(grade) >= 3
    expected_time_seconds = get_expected_time_seconds(srs_record.student)
    normalized_time = normalize_active_time_seconds(active_time_seconds)
    signal = determine_fsrs_signal(
        is_correct=is_correct,
        active_time_seconds=normalized_time,
        attempt_count=attempt_count,
        expected_time_seconds=expected_time_seconds,
    )

    next_state = review_card(srs_record.fsrs_state, signal)
    due_iso = next_state["due"]
    due_dt = datetime.fromisoformat(due_iso)

    srs_record.srs_algorithm = "fsrs"
    srs_record.fsrs_state = next_state
    srs_record.last_grade = grade
    srs_record.last_reviewed_at = timezone.now()
    srs_record.next_review_date = due_dt.date()
    srs_record.save(update_fields=[
        "srs_algorithm",
        "fsrs_state",
        "last_grade",
        "last_reviewed_at",
        "next_review_date",
    ])
    return srs_record
```

- [ ] **Step 5: Run both service test files**

Run: `python manage.py test core.tests.test_fsrs_review_signal core.tests.test_fsrs_soft_migration -v 2`

Expected: PASS for the new signal tests and the soft-migration tests.

- [ ] **Step 6: Commit the signal logic**

```bash
git add core/services.py core/fsrs_engine.py core/tests/test_fsrs_review_signal.py core/tests/test_fsrs_soft_migration.py
git commit -m "feat: map binary reviews to fsrs signals"
```

### Task 3: Collect Real Active Solve Time In SRS Practice

**Files:**
- Create: `core/tests/test_student_practice_srs_active_time.py`
- Modify: `core/templates/core/student_practice.html`
- Modify: `core/views.py`
- Modify: `core/tests/test_practice_answer_lock.py`

- [ ] **Step 1: Write the failing integration tests for active time capture**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, SpacedRepetition, Subject, Task, TaskLog, TaskType, TaskVariant, Topic, User


class StudentPracticeSrsActiveTimeTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="clock_s", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тест", max_points=1)
        topic = Topic.objects.create(subject=subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="7", difficulty=20, exam_points=1)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
        SpacedRepetition.objects.create(student=self.student, task=self.task, next_review_date=timezone.localdate())

    def test_posted_active_time_is_saved_to_tasklog(self):
        self.client.force_login(self.student)
        self.client.get(reverse("student_practice") + "?mode=srs")
        token = self.client.session.get("practice_current", {}).get("token")

        res = self.client.post(
            reverse("student_practice"),
            {
                "task_id": self.task.id,
                "answer": "7",
                "mode": "srs",
                "attempt_token": token,
                "active_time_seconds": "97",
                "attempt_count": "1",
            },
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(TaskLog.objects.filter(student=self.student, task=self.task).latest("id").time_spent, 97)

    def test_invalid_active_time_falls_back_without_crashing(self):
        self.client.force_login(self.student)
        self.client.get(reverse("student_practice") + "?mode=srs")
        token = self.client.session.get("practice_current", {}).get("token")

        res = self.client.post(
            reverse("student_practice"),
            {
                "task_id": self.task.id,
                "answer": "0",
                "mode": "srs",
                "attempt_token": token,
                "active_time_seconds": "-25",
                "attempt_count": "3",
            },
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(TaskLog.objects.filter(student=self.student, task=self.task).latest("id").time_spent, 60)
```

- [ ] **Step 2: Run the new view test**

Run: `python manage.py test core.tests.test_student_practice_srs_active_time -v 2`

Expected: FAIL because `active_time_seconds` and `attempt_count` are ignored and `TaskLog.time_spent` remains `60`.

- [ ] **Step 3: Add hidden fields and the timer script to the practice template**

```html
<!-- core/templates/core/student_practice.html -->
<input type="hidden" name="active_time_seconds" value="0" data-active-time-seconds>
<input type="hidden" name="attempt_count" value="1" data-attempt-count>
```

```html
<script>
document.addEventListener('DOMContentLoaded', () => {
    const activeInputs = Array.from(document.querySelectorAll('[data-active-time-seconds]'));
    const attemptInputs = Array.from(document.querySelectorAll('[data-attempt-count]'));
    if (!activeInputs.length) return;

    let activeSeconds = 0;
    let visibleAt = document.hidden ? null : Date.now();
    const startedAt = Date.now();

    function flushActiveTime() {
        if (visibleAt === null) return;
        const delta = Math.max(0, Math.floor((Date.now() - visibleAt) / 1000));
        activeSeconds += delta;
        visibleAt = Date.now();
    }

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            flushActiveTime();
            visibleAt = null;
        } else {
            visibleAt = Date.now();
        }
    });

    window.addEventListener('beforeunload', flushActiveTime);

    document.querySelectorAll('form[action="{% url "student_practice" %}"]').forEach((form) => {
        form.addEventListener('submit', () => {
            flushActiveTime();
            const fallback = Math.max(1, Math.floor((Date.now() - startedAt) / 1000));
            const finalSeconds = Math.max(activeSeconds, fallback);
            activeInputs.forEach((input) => { input.value = String(finalSeconds); });
            attemptInputs.forEach((input) => { input.value = input.value || "1"; });
        });
    });
});
</script>
```

- [ ] **Step 4: Read the posted fields in `student_practice`**

```python
# core/views.py
active_time_seconds = request.POST.get("active_time_seconds")
attempt_count_raw = request.POST.get("attempt_count")
try:
    attempt_count = max(1, int(attempt_count_raw or "1"))
except ValueError:
    attempt_count = 1

normalized_time = normalize_active_time_seconds(active_time_seconds)
time_spent = normalized_time if normalized_time is not None else 60
```

```python
# core/views.py
record_task_log(request.user, task, submission, None, time_spent)

if mode == 'srs':
    process_task_submission(
        request.user,
        task,
        grade,
        active_time_seconds=time_spent,
        attempt_count=attempt_count,
    )
```

- [ ] **Step 5: Extend the lock test to assert the new fields do not break idempotency**

```python
res1 = self.client.post(url, {
    "task_id": self.task.id,
    "answer": "1",
    "attempt_token": token,
    "mode": "srs",
    "active_time_seconds": "44",
    "attempt_count": "1",
})
```

```python
res2 = self.client.post(url, {
    "task_id": self.task.id,
    "answer": "2",
    "attempt_token": token,
    "mode": "srs",
    "active_time_seconds": "48",
    "attempt_count": "2",
})
```

- [ ] **Step 6: Run the focused practice tests**

Run: `python manage.py test core.tests.test_student_practice_srs_active_time core.tests.test_practice_answer_lock core.tests.test_student_practice_srs_mode_persists -v 2`

Expected: PASS, including the new `TaskLog.time_spent` assertion.

- [ ] **Step 7: Commit active-time capture**

```bash
git add core/templates/core/student_practice.html core/views.py core/tests/test_student_practice_srs_active_time.py core/tests/test_practice_answer_lock.py core/tests/test_student_practice_srs_mode_persists.py
git commit -m "feat: capture active solve time for srs reviews"
```

### Task 4: Switch The SRS Review Flow To FSRS Everywhere

**Files:**
- Modify: `core/services.py`
- Modify: `core/views.py`
- Modify: `core/tests/test_tutor_dashboard_srs_counters.py`
- Modify: `core/tests/test_fsrs_soft_migration.py`

- [ ] **Step 1: Write the failing regression test for dashboard-compatible review updates**

```python
from django.test import TestCase
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, Subject, Task, TaskType, Topic, User
from core.services import process_srs_review


class TutorDashboardSrsCountersTests(TestCase):
    def test_process_srs_review_sets_last_reviewed_at_and_fsrs_algorithm(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        student.tutors.add(tutor)
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тест", max_points=1)
        topic = Topic.objects.create(subject=subject, name="T")
        task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="1", difficulty=10, exam_points=1)

        rec = SpacedRepetition.objects.create(student=student, task=task, next_review_date=timezone.localdate())
        before = timezone.now()

        process_srs_review(rec, grade=5, active_time_seconds=25, attempt_count=1)
        rec.refresh_from_db()

        self.assertIsNotNone(rec.last_reviewed_at)
        self.assertGreaterEqual(rec.last_reviewed_at, before)
        self.assertEqual(rec.srs_algorithm, "fsrs")
```

- [ ] **Step 2: Run the regression test**

Run: `python manage.py test core.tests.test_tutor_dashboard_srs_counters -v 2`

Expected: FAIL until the review flow updates the new fields and keeps old dashboard expectations green.

- [ ] **Step 3: Remove the old SM-2 branch from `process_srs_review()` and centralize fallbacks**

```python
# core/services.py
def process_srs_review(srs_record, grade, *, active_time_seconds=None, attempt_count=1):
    try:
        return _process_fsrs_review(
            srs_record,
            grade=grade,
            active_time_seconds=active_time_seconds,
            attempt_count=attempt_count,
        )
    except Exception:
        srs_record.last_grade = grade
        srs_record.last_reviewed_at = timezone.now()
        srs_record.next_review_date = timezone.localdate() + timedelta(days=1)
        srs_record.save(update_fields=["last_grade", "last_reviewed_at", "next_review_date"])
        return srs_record
```

```python
# core/services.py
def _process_fsrs_review(srs_record, *, grade, active_time_seconds=None, attempt_count=1):
    is_correct = int(grade) >= 3
    signal = determine_fsrs_signal(
        is_correct=is_correct,
        active_time_seconds=normalize_active_time_seconds(active_time_seconds),
        attempt_count=attempt_count,
        expected_time_seconds=get_expected_time_seconds(srs_record.student),
    )
    next_state = review_card(srs_record.fsrs_state, signal)
    due_dt = datetime.fromisoformat(next_state["due"])
    srs_record.srs_algorithm = "fsrs"
    srs_record.fsrs_state = next_state
    srs_record.last_grade = int(grade)
    srs_record.last_reviewed_at = timezone.now()
    srs_record.next_review_date = due_dt.date()
    srs_record.save(update_fields=["srs_algorithm", "fsrs_state", "last_grade", "last_reviewed_at", "next_review_date"])
    return srs_record
```

- [ ] **Step 4: Make sure all `mode=srs` entry points pass the richer review context**

```python
# core/views.py in student_practice()
process_task_submission(
    request.user,
    task,
    grade,
    active_time_seconds=time_spent,
    attempt_count=attempt_count,
)
```

```python
# core/views.py in AI-verification branches that already call process_task_submission()
process_task_submission(
    submission.student,
    submission.task,
    grade,
    active_time_seconds=60,
    attempt_count=1,
)
```

- [ ] **Step 5: Run the regression suite around SRS review paths**

Run: `python manage.py test core.tests.test_tutor_dashboard_srs_counters core.tests.test_srs_from_assignments core.tests.test_srs_partial_points core.tests.test_ai_verify_partial_score_adds_srs -v 2`

Expected: PASS, confirming that due counters, assignment-created SRS rows, partial-score handling, and AI verification still work.

- [ ] **Step 6: Commit the FSRS switch**

```bash
git add core/services.py core/views.py core/tests/test_tutor_dashboard_srs_counters.py core/tests/test_fsrs_soft_migration.py
git commit -m "feat: switch srs reviews to fsrs"
```

### Task 5: Run Diagnostics, Tighten Edge Cases, And Document Rollout

**Files:**
- Modify: `core/services.py`
- Modify: `core/views.py`
- Modify: `docs/superpowers/specs/2026-06-09-fsrs-design.md` (only if reality diverges from the spec during implementation)

- [ ] **Step 1: Run the full SRS- and practice-related test slice**

Run: `python manage.py test core.tests.test_fsrs_review_signal core.tests.test_fsrs_soft_migration core.tests.test_student_practice_srs_active_time core.tests.test_practice_answer_lock core.tests.test_student_practice_srs_mode_persists core.tests.test_tutor_dashboard_srs_counters core.tests.test_srs_from_assignments core.tests.test_srs_partial_points core.tests.test_ai_verify_partial_score_adds_srs -v 2`

Expected: PASS for the whole FSRS migration slice.

- [ ] **Step 2: Run lints/diagnostics on edited files**

Run: `python -m compileall core && ruff check core/models.py core/services.py core/views.py core/fsrs_engine.py core/tests/test_fsrs_review_signal.py core/tests/test_fsrs_soft_migration.py core/tests/test_student_practice_srs_active_time.py core/tests/test_tutor_dashboard_srs_counters.py`

Expected: `Compiling 'core/...': OK` and `All checks passed!`

- [ ] **Step 3: Add the last two guardrails if tests reveal drift**

```python
# core/services.py
def normalize_active_time_seconds(value):
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return min(seconds, 3600)
```

```python
# core/views.py
try:
    attempt_count = max(1, int(request.POST.get("attempt_count") or "1"))
except ValueError:
    attempt_count = 1
```

- [ ] **Step 4: If implementation required a spec adjustment, update the spec before final handoff**

```markdown
## Реализованное отклонение

- На первом этапе `expected_time_seconds` считается по средней, а не по медиане, потому что в текущем коде уже есть готовый путь через `Avg("time_spent")`.
- Повторная отправка ответа по тому же `attempt_token` не увеличивает `attempt_count`, потому что результат возвращается из session-lock и не должен менять review.
```

- [ ] **Step 5: Commit the stabilized rollout**

```bash
git add core/services.py core/views.py core/fsrs_engine.py core/models.py core/templates/core/student_practice.html core/tests docs/superpowers/specs/2026-06-09-fsrs-design.md
git commit -m "feat: finish fsrs migration rollout"
```

## Self-Review

- Spec coverage:
  - `FSRS` engine and hidden signal mapping are implemented in Tasks 1, 2, and 4.
  - Real `active_time_seconds` collection is implemented in Task 3.
  - Soft migration for legacy `SM-2` rows is covered in Tasks 1 and 4.
  - Queue compatibility via `next_review_date` is preserved in Tasks 1 and 4.
  - Error/fallback behavior is covered in Task 4 and hardened in Task 5.
- Placeholder scan:
  - No `TODO`, `TBD`, or “write tests later” markers remain.
  - Every code-changing step includes concrete code and an exact command.
- Type consistency:
  - `process_task_submission(..., active_time_seconds=..., attempt_count=...)` is used consistently across tasks.
  - `determine_fsrs_signal()` returns only `again`, `hard`, or `good`.
  - `SpacedRepetition.srs_algorithm` uses only `sm2` and `fsrs`.
