# Student UX Bugfixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix assignment finishing (incl. part-2 confirmation), surface deadline urgency, stabilize chat input visibility, enforce valid OGE 1–5 bundles, and show SRS remaining count + ETA.

**Architecture:** Keep existing Django views/templates; add small, explicit server-side flags into template contexts for confirmation/UX. For OGE bundles, constrain selection to validated `bundle_code` sets and ship a safe cleanup management command.

**Tech Stack:** Django (views/templates/tests), SQLite/Postgres compatible ORM, Tailwind in templates.

---

## File map

**Assignment finish + deadlines**
- Modify: [views.py](file:///workspace/core/views.py) (`student_solve_assignment`, `student_dashboard`, `api_student_pending_assignments`)
- Modify: [student_solve_assignment.html](file:///workspace/core/templates/core/student_solve_assignment.html)
- Modify: [student_dashboard.html](file:///workspace/core/templates/core/student_dashboard.html)
- Test: `core/tests/test_student_solve_assignment_force_finish_part2.py` (new)
- Test: `core/tests/test_student_dashboard_deadline_badges.py` (new)

**Chat**
- Modify: [views_chat.py](file:///workspace/core/views_chat.py)
- Modify: [chat.html](file:///workspace/core/templates/core/chat.html)
- Test: extend [test_chat_input_visible.py](file:///workspace/core/tests/test_chat_input_visible.py) or add `core/tests/test_chat_index_autoselects_dialog.py`

**OGE bundles**
- Modify: [views.py](file:///workspace/core/views.py) (`tutor_create_assignment`, bundle selection block)
- Create: `core/management/commands/clean_oge_bundles_1_5.py`
- Test: extend [test_tutor_assignment_bundle_selection.py](file:///workspace/core/tests/test_tutor_assignment_bundle_selection.py) + add `core/tests/test_oge_bundle_only_valid_codes_selected.py`

**SRS remaining + ETA**
- Modify: [views.py](file:///workspace/core/views.py) (`student_practice`, optionally `student_dashboard`)
- Modify: [student_practice.html](file:///workspace/core/templates/core/student_practice.html)
- Modify: [student_practice_result.html](file:///workspace/core/templates/core/student_practice_result.html)
- Test: `core/tests/test_student_practice_srs_shows_remaining_and_eta.py` (new)

---

## Task 1: Assignment finish works without JS + part-2 “force finish” confirmation

**Files:**
- Modify: [views.py](file:///workspace/core/views.py#L1370-L1510)
- Modify: [student_solve_assignment.html](file:///workspace/core/templates/core/student_solve_assignment.html#L67-L566)
- Test: `core/tests/test_student_solve_assignment_force_finish_part2.py`

- [ ] **Step 1: Write failing test (confirmation required, then force finish completes)**

Create `core/tests/test_student_solve_assignment_force_finish_part2.py`:

```python
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User


class StudentSolveAssignmentForceFinishPart2Tests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subj, name="T")

        tt_part2 = TaskType.objects.create(
            exam_format=ef, number=20, name="2 часть", max_points=2, is_extended_answer=True
        )
        self.part2_task = Task.objects.create(
            topic=topic, task_type=tt_part2, correct_answer="x", difficulty=10, exam_points=2
        )

        self.assignment = Assignment.objects.create(
            tutor=self.tutor,
            student=self.student,
            title="A",
            is_draft=False,
            is_deleted=False,
            due_date=timezone.now().date(),
            exam_format=ef,
        )
        self.assignment.tasks.add(self.part2_task)

    def test_finish_requires_confirmation_when_part2_missing_photo(self):
        self.client.login(username="s", password="pass")
        res = self.client.post(
            reverse("student_solve_assignment", args=[self.assignment.id]),
            data={"action": "finish"},
        )
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")
        self.assertIn("Завершить всё равно", html)

        self.assignment.refresh_from_db()
        self.assertFalse(self.assignment.is_completed)

    def test_force_finish_completes_assignment(self):
        self.client.login(username="s", password="pass")
        res = self.client.post(
            reverse("student_solve_assignment", args=[self.assignment.id]),
            data={"action": "finish", "force_finish": "1"},
            follow=False,
        )
        self.assertIn(res.status_code, (302, 303))
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_completed)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python manage.py test core.tests.test_student_solve_assignment_force_finish_part2 -v 2
```

Expected: FAIL (currently finish is blocked with redirect, not a confirmation page).

- [ ] **Step 3: Implement server-side confirmation flow in `student_solve_assignment`**

Modify [student_solve_assignment](file:///workspace/core/views.py#L1370-L1510) to:
- Accept `force_finish = (request.POST.get("force_finish") == "1")`
- When `action == "finish"` and missing part-2 photos exist and `not force_finish`:
  - render the same template with extra context keys:
    - `needs_force_finish=True`
    - `missing_part2_tasks=[...]`
  - do not redirect
  - do not set `assignment.is_completed`

Patch sketch (core logic only):

```python
if action == "finish":
    force_finish = (request.POST.get("force_finish") == "1")
    missing_part2 = []
    for t in tasks:
        if is_extended_answer_task(t):
            sub = subs_by_task_id.get(t.id)
            if not sub or not sub.image_url:
                missing_part2.append(t)
    if missing_part2 and not force_finish:
        tasks_list = list(tasks)
        # existing code already builds task.saved_submission etc. for GET;
        # for POST re-render, reuse saved_submissions/subs_by_task_id and attach to tasks_list similarly.
        return render(request, "core/student_solve_assignment.html", {
            "assignment": assignment,
            "tasks": tasks_list,
            "needs_force_finish": True,
            "missing_part2_tasks": missing_part2,
            "unread_tutor_replies_total": unread_tutor_replies_total,
        })
```

- [ ] **Step 4: Make the “Завершить вариант” action not depend on JS**

Modify [student_solve_assignment.html](file:///workspace/core/templates/core/student_solve_assignment.html#L546-L566):
- Replace current `type="button"` buttons + hidden `action` with submit buttons:

```html
<button type="submit" name="action" value="postpone" class="...">
  <i class="fas fa-pause mr-2"></i> Отложить решение
</button>

<button type="submit" name="action" value="finish" class="...">
  <i class="fas fa-flag-checkered mr-2"></i> Завершить вариант
</button>
```

- [ ] **Step 5: Add visible confirmation UI when `needs_force_finish`**

In [student_solve_assignment.html](file:///workspace/core/templates/core/student_solve_assignment.html):
- Add an alert block near the top (after header) when `needs_force_finish`:
  - list `missing_part2_tasks` numbers/titles
  - add a small form control `force_finish=1` button (submit `action=finish`)

HTML sketch:

```html
{% if needs_force_finish %}
  <div class="mb-6 bg-yellow-50 border border-yellow-200 text-yellow-900 rounded-xl p-4">
    <div class="font-bold">Не все задания 2-й части сданы</div>
    <div class="text-sm mt-1">Нет фото по задачам:
      {% for t in missing_part2_tasks %}<span class="font-bold">№{{ forloop.counter }}</span>{% if not forloop.last %}, {% endif %}{% endfor %}
    </div>
    <div class="mt-3 flex gap-2">
      <button type="submit" name="action" value="finish" name="force_finish" value="1" class="bg-primary text-white px-4 py-2 rounded-lg font-bold">Завершить всё равно</button>
      <a href="{% url 'student_solve_assignment' assignment.id %}" class="bg-white border border-gray-200 px-4 py-2 rounded-lg font-bold">Вернуться и загрузить фото</a>
    </div>
  </div>
{% endif %}
```

Implementation detail: because HTML cannot have duplicate `name` on a button reliably, implement the force confirm as:

```html
<button type="submit" name="action" value="finish" class="...">Завершить всё равно</button>
<input type="hidden" name="force_finish" value="1">
```

…inside a small secondary `<form>` (recommended), or conditionally inject the hidden input when needs_force_finish is true.

- [ ] **Step 6: Add `messages` block to this template**

Copy the message rendering pattern from [student_dashboard.html](file:///workspace/core/templates/core/student_dashboard.html#L62-L70) into `student_solve_assignment.html` so warnings/success are visible.

- [ ] **Step 7: Run tests**

```bash
python manage.py test core.tests.test_student_solve_assignment_force_finish_part2 -v 2
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/views.py core/templates/core/student_solve_assignment.html core/tests/test_student_solve_assignment_force_finish_part2.py
git commit -m "fix: allow assignment finish with part2 confirmation"
```

---

## Task 2: Deadline highlighting + due date visibility on student dashboard (threshold: 1 day)

**Files:**
- Modify: [views.py](file:///workspace/core/views.py) (`student_dashboard`, `api_student_pending_assignments`)
- Modify: [student_dashboard.html](file:///workspace/core/templates/core/student_dashboard.html)
- Test: `core/tests/test_student_dashboard_deadline_badges.py`

- [ ] **Step 1: Write failing test for “due soon” badge and sorting**

Create `core/tests/test_student_dashboard_deadline_badges.py`:

```python
import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, Topic, User


class StudentDashboardDeadlineBadgesTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1, is_extended_answer=False)
        topic = Topic.objects.create(subject=subj, name="T")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)

        today = timezone.now().date()
        self.a_soon = Assignment.objects.create(tutor=self.tutor, student=self.student, title="Soon", is_draft=False, due_date=today)
        self.a_later = Assignment.objects.create(tutor=self.tutor, student=self.student, title="Later", is_draft=False, due_date=today + datetime.timedelta(days=10))
        self.a_none = Assignment.objects.create(tutor=self.tutor, student=self.student, title="NoDue", is_draft=False, due_date=None)
        for a in (self.a_soon, self.a_later, self.a_none):
            a.tasks.add(task)

    def test_dashboard_marks_due_soon_and_sorts(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("student_dashboard"))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")
        self.assertIn("Срок", html)
        self.assertIn("Срок сегодня/завтра", html)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test core.tests.test_student_dashboard_deadline_badges -v 2
```

- [ ] **Step 3: Implement ordering + flags in `student_dashboard`**

In `student_dashboard`:
- Sort `pending_assignments` by `due_date` asc with nulls last.
- Compute for each assignment:
  - `is_due_overdue`
  - `is_due_soon` (`due_date <= today + 1 day` and not overdue)

Expose those flags into template context (attach as attributes or build view-model list).

- [ ] **Step 4: Render date + badge in template**

In [student_dashboard.html](file:///workspace/core/templates/core/student_dashboard.html):
- Show `due_date` visibly for each pending assignment.
- If `is_due_soon` show badge text “Срок сегодня/завтра”.
- If overdue show “Просрочено”.

- [ ] **Step 5: Keep API consistent**

Update `api_student_pending_assignments` to return due date + urgency flag so the frontend can match dashboard behavior.

- [ ] **Step 6: Run tests**

```bash
python manage.py test core.tests.test_student_dashboard_deadline_badges -v 2
```

- [ ] **Step 7: Commit**

```bash
git add core/views.py core/templates/core/student_dashboard.html core/tests/test_student_dashboard_deadline_badges.py
git commit -m "feat: highlight assignment deadlines on student dashboard"
```

---

## Task 3: Chat input is always visible when dialogs exist (auto-select + clear empty-state)

**Files:**
- Modify: [views_chat.py](file:///workspace/core/views_chat.py)
- Modify: [chat.html](file:///workspace/core/templates/core/chat.html)
- Test: `core/tests/test_chat_index_autoselects_dialog.py` (new)

- [ ] **Step 1: Write failing test (chat index auto-selects first dialog)**

Create `core/tests/test_chat_index_autoselects_dialog.py`:

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, Subject, ExamFormat, Topic, TaskType, Task, User


class ChatIndexAutoselectsDialogTests(TestCase):
    def test_chat_index_autoselects_first_dialog(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        student.tutors.add(tutor)

        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subj, name="T")
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1, is_extended_answer=False)
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        a = Assignment.objects.create(tutor=tutor, student=student, title="A", is_draft=False)
        a.tasks.add(task)

        self.client.login(username="t", password="pass")
        r = self.client.get(reverse("chat_index"))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertIn("chat-input", html)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test core.tests.test_chat_index_autoselects_dialog -v 2
```

- [ ] **Step 3: Implement auto-select in `chat_index`**

In `views_chat.chat_index`:
- If `dialogs` is not empty and `active_dialog` is None, set `active_dialog = dialogs[0]`.

- [ ] **Step 4: Add explicit empty-state in `chat.html`**

In [chat.html](file:///workspace/core/templates/core/chat.html):
- If no dialogs: show a clear message (not just missing input).
- If dialogs exist but no active dialog (should be rare after Step 3): show a fallback UI with instruction.

- [ ] **Step 5: Run tests**

```bash
python manage.py test core.tests.test_chat_index_autoselects_dialog -v 2
python manage.py test core.tests.test_chat_input_visible -v 2
```

- [ ] **Step 6: Commit**

```bash
git add core/views_chat.py core/templates/core/chat.html core/tests/test_chat_index_autoselects_dialog.py
git commit -m "fix: stabilize chat input by auto-selecting dialog"
```

---

## Task 4: OGE 1–5 bundles — select only valid bundle_code + add safe cleanup command

**Files:**
- Modify: [views.py](file:///workspace/core/views.py) (`tutor_create_assignment` bundle selection block)
- Create: `core/management/commands/clean_oge_bundles_1_5.py`
- Test: `core/tests/test_oge_bundle_only_valid_codes_selected.py`

- [ ] **Step 1: Write failing test for “invalid bundle not selected”**

Create `core/tests/test_oge_bundle_only_valid_codes_selected.py`:

```python
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, Subject, Task, TaskType, Topic, User


class OgeBundleOnlyValidCodesSelectedTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        subj = Subject.objects.create(name="Математика")
        self.ef = ExamFormat.objects.create(subject=subj, name="ОГЭ", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subj, name="T")
        self.tt = {}
        for n in range(1, 6):
            self.tt[n] = TaskType.objects.create(exam_format=self.ef, number=n, name=str(n), max_points=1, is_extended_answer=False)

        # valid bundle: has 1..5
        for n in range(1, 6):
            Task.objects.create(topic=topic, task_type=self.tt[n], correct_answer="1", difficulty=10, exam_points=1, bundle_code="B_VALID")

        # invalid bundle: missing #4
        for n in (1, 2, 3, 5):
            Task.objects.create(topic=topic, task_type=self.tt[n], correct_answer="1", difficulty=10, exam_points=1, bundle_code="B_BAD")

    def test_generator_uses_only_valid_bundle(self):
        self.client.login(username="t", password="pass")
        res = self.client.post(
            reverse("tutor_create_assignment"),
            data={
                "student_id": self.student.id,
                "title": "A",
                "exam_format_id": self.ef.id,
                "subject_id": self.ef.subject_id,
                # request 1 bundle via type #1 count
                f"type_count_{self.tt[1].id}": "1",
            },
            follow=False,
        )
        self.assertIn(res.status_code, (302, 303))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test core.tests.test_oge_bundle_only_valid_codes_selected -v 2
```

- [ ] **Step 3: Implement “valid bundle code” filter in generator**

In [tutor_create_assignment bundle block](file:///workspace/core/views.py#L3098-L3186):
- Before selecting random anchor tasks, compute `valid_bundle_codes`:
  - consider only tasks with `task_type.number in 1..5` and non-empty `bundle_code`
  - group by `bundle_code` and keep only those with exactly 5 tasks and 5 distinct numbers
- When sampling bundles, restrict to `bundle_code__in=valid_bundle_codes`.

Implementation approach: ORM aggregation with `Count` + `distinct` and/or explicit per-number counts.

- [ ] **Step 4: Add management command `clean_oge_bundles_1_5` (dry-run default)**

Create `core/management/commands/clean_oge_bundles_1_5.py` that:
- finds invalid `bundle_code` (same validation rule as generator)
- when `--apply` is set, sets `bundle_code=None` for tasks (numbers 1..5) in invalid bundles
- prints summary counts either way

- [ ] **Step 5: Run tests**

```bash
python manage.py test core.tests.test_oge_bundle_only_valid_codes_selected -v 2
python manage.py test core.tests.test_tutor_assignment_bundle_selection -v 2
```

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/management/commands/clean_oge_bundles_1_5.py core/tests/test_oge_bundle_only_valid_codes_selected.py
git commit -m "fix: select only valid OGE 1-5 bundles + add cleanup command"
```

---

## Task 5: SRS — show remaining count and ETA in practice UI

**Files:**
- Modify: [views.py](file:///workspace/core/views.py#L629-L796) (`student_practice`)
- Modify: [student_practice.html](file:///workspace/core/templates/core/student_practice.html)
- Modify: [student_practice_result.html](file:///workspace/core/templates/core/student_practice_result.html)
- Test: `core/tests/test_student_practice_srs_shows_remaining_and_eta.py`

- [ ] **Step 1: Write failing test**

Create `core/tests/test_student_practice_srs_shows_remaining_and_eta.py`:

```python
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, Subject, Task, TaskLog, TaskType, TaskVariant, Topic, User


class StudentPracticeSrsShowsRemainingAndEtaTests(TestCase):
    def test_srs_shows_remaining_and_eta(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1, is_extended_answer=False)
        topic = Topic.objects.create(subject=subj, name="T")

        tasks = []
        for i in range(3):
            t = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
            TaskVariant.objects.create(task=t, theme="classic", content="<p>Q</p>", solution="<p>S</p>")
            SpacedRepetition.objects.create(student=student, task=t, next_review_date=timezone.now().date())
            tasks.append(t)

        # baseline avg time: 60 sec from existing logging convention
        TaskLog.objects.create(student=student, task=tasks[0], time_spent=60, score=1.0, is_anomaly=False)

        self.client.force_login(student)
        r = self.client.get(reverse("student_practice") + "?mode=srs")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertIn("Сегодня повторить", html)
        self.assertIn("≈", html)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test core.tests.test_student_practice_srs_shows_remaining_and_eta -v 2
```

- [ ] **Step 3: Implement due count + ETA in `student_practice`**

In GET branch (`mode == 'srs'`):
- compute `due_qs = get_due_tasks_for_student(user)`
- set:
  - `srs_due_total = due_qs.count()`
  - `srs_due_left_after_current = max(0, srs_due_total - (1 if task else 0))`
  - `srs_eta_minutes = ...` based on recent `TaskLog.time_spent` median/avg

Pass these into template context.

- [ ] **Step 4: Render in `student_practice.html`**

Add a small line near “Повторить сегодня”:
- `Сегодня повторить: {{ srs_due_total }}`
- `После этой останется: {{ srs_due_left_after_current }}`
- `≈ {{ srs_eta_minutes }} мин`

- [ ] **Step 5: (Optional) Also show on result page**

After POST in `student_practice`, when rendering result, add the updated `due_after = get_due_tasks_for_student(user).count()` and show “Осталось: N”.

- [ ] **Step 6: Run tests**

```bash
python manage.py test core.tests.test_student_practice_srs_shows_remaining_and_eta -v 2
python manage.py test core.tests.test_student_practice_srs_mode_persists -v 2
```

- [ ] **Step 7: Commit**

```bash
git add core/views.py core/templates/core/student_practice.html core/templates/core/student_practice_result.html core/tests/test_student_practice_srs_shows_remaining_and_eta.py
git commit -m "feat: show SRS remaining count and ETA"
```

---

## Plan self-review checklist

- [ ] Coverage: Task 1 covers finish/confirmation/messages; Task 2 covers deadlines; Task 3 covers chat input; Task 4 covers OGE bundles + cleanup; Task 5 covers SRS remaining/ETA.
- [ ] No placeholders: verify no “TBD/TODO” remain.
- [ ] Names match codebase: URL names used in tests exist (`student_solve_assignment`, `tutor_create_assignment`, `chat_index`, `student_practice`).
