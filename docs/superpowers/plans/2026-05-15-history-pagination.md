# History Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить пагинацию в журнал решений ученика и историю решений ученика у репетитора, сохранив deep-link по `submission_id`.

**Architecture:**  
- Ученик: пагинация по `Submission` (20/страница) через `django.core.paginator.Paginator`.  
- Репетитор: пагинация по дням (14 дней/страница). Список дней получаем в БД через `TruncDate(..., tzinfo=current_tz)`, затем грузим `Submission` только для дней текущей страницы. Deep-link `submission_id` вычисляет нужную страницу и делает redirect на неё.

**Tech Stack:** Django (views + templates), Django TestCase.

---

## Map of changes (files)

**Modify:**
- `core/views.py` — `student_history`, `tutor_student_history`
- `core/templates/core/student_history.html` — UI пагинации + корректное отображение баллов (по желанию отдельным PR, но сейчас только пагинация)
- `core/templates/core/tutor_student_history.html` — UI пагинации (по дням), сохранение `submission_id` в ссылках

**Create:**
- `core/tests/test_student_history_pagination.py`
- `core/tests/test_tutor_student_history_pagination.py`

---

## Task 1: Student history — пагинация по решениям (20 на страницу)

**Files:**
- Modify: `core/views.py` (`student_history`)
- Modify: `core/templates/core/student_history.html`
- Test: `core/tests/test_student_history_pagination.py`

- [ ] **Step 1: Write failing test**

Create `core/tests/test_student_history_pagination.py`:

```python
from django.test import TestCase
from core.models import User, Subject, Topic, Task, TaskVariant, Submission


class StudentHistoryPaginationTests(TestCase):
    def test_student_history_paginated_20_per_page(self):
        student = User.objects.create_user(username="s1", password="pw", role="student")
        subject = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, correct_answer="1", exam_points=1)
        TaskVariant.objects.create(task=task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        for i in range(25):
            Submission.objects.create(student=student, task=task, user_answer=str(i), is_correct=False, score=0)

        self.client.force_login(student)

        res1 = self.client.get("/history/")
        self.assertEqual(res1.status_code, 200)
        self.assertIn("page_obj", res1.context)
        self.assertEqual(len(res1.context["submissions"]), 20)

        res2 = self.client.get("/history/?page=2")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(len(res2.context["submissions"]), 5)
```

- [ ] **Step 2: Run test to verify RED**

Run:
```bash
python manage.py test core.tests.test_student_history_pagination
```

- [ ] **Step 3: Implement pagination in `student_history`**

Update `core/views.py` (`student_history`):
1) Импорт:
```python
from django.core.paginator import Paginator
```
2) Вместо передачи всего queryset, сделать:
```python
per_page = 20
page_number = (request.GET.get("page") or "1").strip()
page_obj = Paginator(submissions, per_page).get_page(page_number)
submissions_page = list(page_obj.object_list)
```
3) `_mark_student_replies_seen` вызвать на `submissions_page` (а не на весь queryset).
4) В `render` передать:
```python
"submissions": submissions_page,
"page_obj": page_obj,
```

- [ ] **Step 4: Add pagination UI in `student_history.html`**

Внизу страницы (после списка) добавить блок:
```django
{% if page_obj and page_obj.paginator.num_pages > 1 %}
  <div class="mt-6 flex items-center justify-between">
    <div class="text-xs text-gray-500">Страница {{ page_obj.number }} из {{ page_obj.paginator.num_pages }}</div>
    <div class="flex gap-2">
      {% if page_obj.has_previous %}
        <a class="px-3 py-2 text-sm font-bold bg-white border border-gray-200 rounded-lg hover:bg-gray-50"
           href="?page={{ page_obj.previous_page_number }}">Назад</a>
      {% else %}
        <span class="px-3 py-2 text-sm font-bold bg-gray-100 border border-gray-200 rounded-lg text-gray-400">Назад</span>
      {% endif %}
      {% if page_obj.has_next %}
        <a class="px-3 py-2 text-sm font-bold bg-white border border-gray-200 rounded-lg hover:bg-gray-50"
           href="?page={{ page_obj.next_page_number }}">Вперёд</a>
      {% else %}
        <span class="px-3 py-2 text-sm font-bold bg-gray-100 border border-gray-200 rounded-lg text-gray-400">Вперёд</span>
      {% endif %}
    </div>
  </div>
{% endif %}
```

- [ ] **Step 5: Run test to verify GREEN**

Run:
```bash
python manage.py test core.tests.test_student_history_pagination
```

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/templates/core/student_history.html core/tests/test_student_history_pagination.py
git commit -m "feat(history): paginate student journal"
```

---

## Task 2: Tutor student history — пагинация по дням (14 дней) + deep-link redirect

**Files:**
- Modify: `core/views.py` (`tutor_student_history`)
- Modify: `core/templates/core/tutor_student_history.html`
- Test: `core/tests/test_tutor_student_history_pagination.py`

- [ ] **Step 1: Write failing tests**

Create `core/tests/test_tutor_student_history_pagination.py`:

```python
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import User, Subject, Topic, Task, TaskVariant, Submission


class TutorStudentHistoryPaginationTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t1", password="pw", role="tutor")
        self.student = User.objects.create_user(username="s1", password="pw", role="student")
        self.tutor.students.add(self.student)

        subject = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, correct_answer="1", exam_points=1)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

    def test_pagination_by_days_14(self):
        now = timezone.now()
        subs = []
        for i in range(20):
            sub = Submission.objects.create(student=self.student, task=self.task, user_answer="1", is_correct=True, score=1)
            Submission.objects.filter(id=sub.id).update(created_at=now - timedelta(days=i))
            subs.append(sub)

        self.client.force_login(self.tutor)
        res1 = self.client.get(f"/tutor/student/{self.student.id}/history/")
        self.assertEqual(res1.status_code, 200)
        self.assertIn("page_obj", res1.context)
        self.assertEqual(len(res1.context["history_days"]), 14)

        res2 = self.client.get(f"/tutor/student/{self.student.id}/history/?page=2")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(len(res2.context["history_days"]), 6)

    def test_deeplink_redirects_to_correct_page(self):
        now = timezone.now()
        target_sub = None
        for i in range(20):
            sub = Submission.objects.create(student=self.student, task=self.task, user_answer="1", is_correct=True, score=1)
            Submission.objects.filter(id=sub.id).update(created_at=now - timedelta(days=i))
            if i == 19:
                target_sub = sub

        self.client.force_login(self.tutor)
        res = self.client.get(f"/tutor/student/{self.student.id}/history/?submission_id={target_sub.id}")
        self.assertEqual(res.status_code, 302)
        self.assertIn("page=2", res["Location"])
        self.assertIn(f"submission_id={target_sub.id}", res["Location"])
```

- [ ] **Step 2: Run tests to verify RED**

Run:
```bash
python manage.py test core.tests.test_tutor_student_history_pagination
```

- [ ] **Step 3: Implement day-list + Paginator + page-load-only**

Update `core/views.py` (`tutor_student_history`):

1) Add imports near the function:
```python
from django.core.paginator import Paginator
from django.db.models.functions import TruncDate
from django.utils import timezone
```

2) Build base queryset (as сейчас):
```python
submissions_qs = (
    Submission.objects.filter(student=student)
    .select_related('task', 'task__task_type', 'assignment')
    .prefetch_related('comments', 'comments__author')
)
```

3) Build day list in **локальной TZ**:
```python
tz = timezone.get_current_timezone()
days_qs = (
    submissions_qs
    .annotate(day=TruncDate("created_at", tzinfo=tz))
    .values_list("day", flat=True)
    .distinct()
    .order_by("-day")
)
days_list = list(days_qs)
```

4) Deep-link redirect:
```python
submission_id_raw = (request.GET.get("submission_id") or "").strip()
page_raw = (request.GET.get("page") or "").strip()

if submission_id_raw.isdigit():
    target = Submission.objects.filter(id=int(submission_id_raw), student=student).only("id", "created_at").first()
    if target:
        target_day = localtime(target.created_at).date()
        index_map = {d: i for i, d in enumerate(days_list)}
        if target_day in index_map:
            target_page = (index_map[target_day] // 14) + 1
            if (not page_raw) or (page_raw.isdigit() and int(page_raw) != target_page):
                return redirect(f"{reverse('tutor_student_history', args=[student.id])}?page={target_page}&submission_id={target.id}")
```

5) Paginate days:
```python
page_obj = Paginator(days_list, 14).get_page(request.GET.get("page") or "1")
page_days = list(page_obj.object_list)
```

6) Load submissions for those days only:
```python
submissions = (
    submissions_qs
    .annotate(day=TruncDate("created_at", tzinfo=tz))
    .filter(day__in=page_days)
    .order_by("-created_at")
)
```

7) Group `submissions` into `history_days` as сейчас (локальная дата через `localtime(sub.created_at).date()`), но уже только для текущих дней.

8) Pass to template:
```python
return render(..., {"student": student, "history_days": history_days, "page_obj": page_obj, "submission_id": submission_id_raw})
```

- [ ] **Step 4: Add pagination UI to tutor template**

В `core/templates/core/tutor_student_history.html` добавить внизу:
```django
{% if page_obj and page_obj.paginator.num_pages > 1 %}
  <div class="mt-6 flex items-center justify-between">
    <div class="text-xs text-gray-500">Страница {{ page_obj.number }} из {{ page_obj.paginator.num_pages }}</div>
    <div class="flex gap-2">
      {% if page_obj.has_previous %}
        <a class="px-3 py-2 text-sm font-bold bg-white border border-gray-200 rounded-lg hover:bg-gray-50"
           href="?page={{ page_obj.previous_page_number }}{% if submission_id %}&submission_id={{ submission_id }}{% endif %}">Назад</a>
      {% else %}
        <span class="px-3 py-2 text-sm font-bold bg-gray-100 border border-gray-200 rounded-lg text-gray-400">Назад</span>
      {% endif %}
      {% if page_obj.has_next %}
        <a class="px-3 py-2 text-sm font-bold bg-white border border-gray-200 rounded-lg hover:bg-gray-50"
           href="?page={{ page_obj.next_page_number }}{% if submission_id %}&submission_id={{ submission_id }}{% endif %}">Вперёд</a>
      {% else %}
        <span class="px-3 py-2 text-sm font-bold bg-gray-100 border border-gray-200 rounded-lg text-gray-400">Вперёд</span>
      {% endif %}
    </div>
  </div>
{% endif %}
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:
```bash
python manage.py test core.tests.test_tutor_student_history_pagination
```

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/templates/core/tutor_student_history.html core/tests/test_tutor_student_history_pagination.py
git commit -m "feat(history): paginate tutor student history by days"
```

---

## Task 3: Regression + merge

- [ ] **Step 1: Run full core tests**

Run:
```bash
python manage.py test core.tests
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

