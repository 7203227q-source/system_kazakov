# Student Dashboard Comments Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить на дашборд ученика панель комментариев (последние 20) с переходом в нужное задание и авто-раскрытием блока вопросов; добавить deep-link `submission_id` в журнал ученика с учётом пагинации.

**Architecture:**  
- В `student_dashboard` выбираем последние `SubmissionComment` ученика, подсвечиваем непрочитанные ответы репетитора.  
- Клик ведёт либо в вариант (`student_solve_assignment`) с `task_id`/`submission_id`, либо в журнал (`student_history`) с `submission_id`.  
- В `student_solve_assignment.html` и `student_history.html` добавляем JS, который по query params раскрывает нужный блок и скроллит.  
- В `student_history` добавляем серверный redirect на правильную страницу пагинации, если `submission_id` на другой странице.

**Tech Stack:** Django (views/templates), JS (минимально), Django TestCase.

---

## Map of changes (files)

**Modify:**
- `core/views.py` — `student_dashboard`, `student_history`
- `core/templates/core/student_dashboard.html` — новый блок “Комментарии”
- `core/templates/core/student_solve_assignment.html` — deep-link: scroll + auto-open chat block
- `core/templates/core/student_history.html` — deep-link: auto-open comments + scroll

**Create:**
- `core/tests/test_student_dashboard_comments_panel.py`
- `core/tests/test_student_history_deeplink_redirect.py`

---

## Task 1: Tests (RED) — дашборд ученика отдаёт комментарии

**Files:**
- Create: `core/tests/test_student_dashboard_comments_panel.py`

- [ ] **Step 1: Write failing test**

```python
from django.test import TestCase

from core.models import User, Subject, Topic, Task, TaskVariant, Submission, SubmissionComment


class StudentDashboardCommentsPanelTests(TestCase):
    def test_student_dashboard_contains_recent_comments(self):
        student = User.objects.create_user(username="s1", password="pw", role="student")
        tutor = User.objects.create_user(username="t1", password="pw", role="tutor")
        student.tutors.add(tutor)

        subject = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, correct_answer="1", exam_points=1)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        sub = Submission.objects.create(student=student, task=task, user_answer="1", is_correct=True, score=1)
        SubmissionComment.objects.create(submission=sub, author=tutor, author_role="tutor", text="Ответ репетитора")

        self.client.force_login(student)
        res = self.client.get("/student/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Комментарии")
        self.assertContains(res, "Ответ репетитора")
```

- [ ] **Step 2: Run test to verify RED**

Run:
```bash
python manage.py test core.tests.test_student_dashboard_comments_panel
```

- [ ] **Step 3: Commit (optional, if you prefer after implementation)**

---

## Task 2: Implement comments panel in `student_dashboard` (GREEN)

**Files:**
- Modify: `core/views.py` (`student_dashboard`)
- Modify: `core/templates/core/student_dashboard.html`
- Test: `core/tests/test_student_dashboard_comments_panel.py`

- [ ] **Step 1: Implement queryset in view**

In `core/views.py::student_dashboard` add:
```python
dashboard_comments_qs = (
    SubmissionComment.objects
    .filter(submission__student=request.user)
    .select_related(
        "author",
        "submission",
        "submission__assignment",
        "submission__task",
        "submission__task__task_type",
    )
    .order_by("-created_at")
)
dashboard_comments_total = dashboard_comments_qs.count()
dashboard_comments = list(dashboard_comments_qs[:20])
for c in dashboard_comments:
    c.is_unread_for_student = (c.author_role == "tutor") and (c.seen_by_student_at is None)
```

Pass to template:
```python
"dashboard_comments": dashboard_comments,
"dashboard_comments_total": dashboard_comments_total,
```

- [ ] **Step 2: Add block UI in template**

In `core/templates/core/student_dashboard.html`, add a section:
- Title “Комментарии”
- “{{ dashboard_comments|length }} из {{ dashboard_comments_total }}” + link to `{% url 'student_history' %}`
- For each `c`:
  - compute target URL:
    - if `c.submission.assignment_id`: `{% url 'student_solve_assignment' c.submission.assignment_id %}?task_id={{ c.submission.task_id }}&submission_id={{ c.submission_id }}`
    - else: `{% url 'student_history' %}?submission_id={{ c.submission_id }}`
  - show badge “новое” if `c.is_unread_for_student`

- [ ] **Step 3: Run test to verify GREEN**

```bash
python manage.py test core.tests.test_student_dashboard_comments_panel
```

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/templates/core/student_dashboard.html core/tests/test_student_dashboard_comments_panel.py
git commit -m "feat(student): show comments panel on dashboard"
```

---

## Task 3: Student history deep-link redirect across pagination (RED → GREEN)

**Files:**
- Create: `core/tests/test_student_history_deeplink_redirect.py`
- Modify: `core/views.py` (`student_history`)
- Modify: `core/templates/core/student_history.html`

- [ ] **Step 1: Write failing test**

```python
from django.test import TestCase

from core.models import User, Subject, Topic, Task, TaskVariant, Submission


class StudentHistoryDeeplinkRedirectTests(TestCase):
    def test_student_history_submission_id_redirects_to_correct_page(self):
        student = User.objects.create_user(username="s1", password="pw", role="student")
        subject = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, correct_answer="1", exam_points=1)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        subs = []
        for i in range(41):  # 20 on page1, 20 on page2, 1 on page3
            subs.append(Submission.objects.create(student=student, task=task, user_answer=str(i), is_correct=False, score=0))

        target = subs[-1]
        self.client.force_login(student)
        res = self.client.get(f"/student/history/?submission_id={target.id}")
        self.assertEqual(res.status_code, 302)
        self.assertIn("page=3", res["Location"])
        self.assertIn(f"submission_id={target.id}", res["Location"])
```

- [ ] **Step 2: Run RED**
```bash
python manage.py test core.tests.test_student_history_deeplink_redirect
```

- [ ] **Step 3: Implement redirect in view**

In `core/views.py::student_history`:
1) Read `submission_id` and `page` from query.
2) If `submission_id` is valid:
   - find target submission `Submission(id=submission_id, student=request.user)` (only `id`, `created_at`)
   - compute how many submissions are newer:
     ```python
     newer_count = submissions_qs.filter(created_at__gt=target.created_at).count()
     target_page = (newer_count // 20) + 1
     ```
   - if request page missing or different → redirect to `?page=<target_page>&submission_id=<id>`
3) Pass `submission_id` to template for JS: `"submission_id": submission_id_raw`

- [ ] **Step 4: Add JS deep-link open in student_history.html**

At bottom of `student_history.html` add:
- read `submission_id`
- open `#comments_sub_<id>` (remove `hidden`)
- scroll into view and add ring highlight for 2.5 sec

- [ ] **Step 5: Run tests GREEN**
```bash
python manage.py test core.tests.test_student_history_deeplink_redirect
```

- [ ] **Step 6: Commit**
```bash
git add core/views.py core/templates/core/student_history.html core/tests/test_student_history_deeplink_redirect.py
git commit -m "feat(student): deeplink to comments in history"
```

---

## Task 4: Student assignment page deep-link (task_id) open chat block

**Files:**
- Modify: `core/templates/core/student_solve_assignment.html`

- [ ] **Step 1: Implement JS**

Add `DOMContentLoaded` block:
1) parse query params `task_id`, `submission_id`
2) if `task_id` exists:
   - find `.task-card[data-task-id="<task_id>"]`
   - scroll into view
   - open chat: call `toggleTaskChat(taskId)` if it exists; else unhide `#chat_block_<taskId>` and `#chat_body_<taskId>`
   - highlight chat body for 2.5 sec

- [ ] **Step 2: Smoke-check test (optional)**

We can keep this without JS unit tests; minimal risk.

- [ ] **Step 3: Commit**

```bash
git add core/templates/core/student_solve_assignment.html
git commit -m "feat(student): deeplink to task chat in assignment"
```

---

## Task 5: Full test run + merge

- [ ] **Step 1: Run full suite**
```bash
python manage.py test core.tests
```

- [ ] **Step 2: Push branch and merge**
```bash
git push origin HEAD
```
Then merge to `main` and push.

