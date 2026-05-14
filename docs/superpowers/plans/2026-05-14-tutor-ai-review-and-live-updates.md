# Tutor AI Review & Live Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Репетитор видит фото решения ученика + вердикт ИИ, может перепроверять ИИ (кулдаун 2 мин) и выставлять «итог репетитора», который заменяет ИИ в аналитике; комментарии из карточки ученика ведут сразу к нужной задаче; новые варианты появляются у ученика без ручного обновления страницы.

**Architecture:** Добавляем поля `Submission.tutor_primary_score/...` и используем их как источник для аналитики; для UI используем существующие страницы (`tutor_assignment_view`, `tutor_student_history`, `student_dashboard`) и лёгкий polling для live-обновления; для репетитора добавляем отдельные API-endpoints для override score и повторной ИИ-проверки с таким же cooldown как у ученика.

**Tech Stack:** Django (views/templates), Tailwind, vanilla JS, existing OpenRouter verify endpoint logic.

---

## Карта файлов (что меняем)

**DB / модели**
- Modify: `core/models.py` (Submission: новые поля)
- Create: `core/migrations/0051_submission_tutor_score_fields.py`

**Аналитика**
- Modify: `core/analytics.py` (учитывать `tutor_primary_score` вместо `primary_score` для мастерства/прогноза)

**API для репетитора**
- Modify: `core/views.py` (2 endpoint’а)
- Modify: `core/urls.py`
- Create tests:
  - `core/tests/test_tutor_override_score_affects_analytics.py`
  - `core/tests/test_tutor_verify_ai_cooldown_and_permissions.py`

**UI репетитора**
- Modify: `core/templates/core/tutor_assignment_view.html` (фото, вердикт ИИ, итог репетитора, кнопка перепроверки ИИ + таймер)

**Deep-link комментариев**
- Modify: `core/views.py` (tutor_dashboard: вычислить `latest_unread_submission_id` для ссылки)
- Modify: `core/templates/core/tutor_dashboard.html` (ссылка с `?submission_id=...`)
- Modify: `core/templates/core/tutor_student_history.html` (авто-раскрытие/скролл по `submission_id`)
- Create test: `core/tests/test_tutor_dashboard_unread_link_points_to_submission.py`

**Live-обновление вариантов у ученика**
- Modify: `core/views.py` (endpoint отдающий pending assignments JSON)
- Modify: `core/urls.py`
- Modify: `core/templates/core/student_dashboard.html` (polling + DOM update)
- Create test: `core/tests/test_student_pending_assignments_api.py`

---

### Task 1: Миграция и модель — поля «итог репетитора»

**Files:**
- Modify: `core/models.py`
- Create: `core/migrations/0051_submission_tutor_score_fields.py`
- Test: `core/tests/test_tutor_override_score_affects_analytics.py`

- [ ] **Step 1: RED — добавить тест, что tutor score используется в аналитике**

Create `core/tests/test_tutor_override_score_affects_analytics.py`:

```python
from django.test import TestCase
from django.utils import timezone
from core.analytics import record_task_log
from core.models import Subject, Topic, ExamFormat, TaskType, Task, User, Submission


class TutorOverrideScoreAffectsAnalyticsTests(TestCase):
    def test_record_task_log_uses_tutor_primary_score_when_present(self):
        subj = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subj, name="T")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=26, name="26", max_points=4)
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=4)

        student = User.objects.create_user(username="s", password="pass", role="student")
        sub = Submission.objects.create(student=student, task=task, is_correct=False, primary_score=1)

        # Репетитор исправил оценку: 3/4
        sub.tutor_primary_score = 3
        sub.save(update_fields=["tutor_primary_score"])

        log = record_task_log(student, task, sub, assignment=None, time_spent=30)
        self.assertEqual(float(log.score), 3.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python manage.py test core.tests.test_tutor_override_score_affects_analytics -v 1
```

Expected: FAIL, потому что `Submission` пока не имеет поля `tutor_primary_score` и/или `record_task_log` использует `primary_score`.

- [ ] **Step 3: GREEN — добавить поля в модель и миграцию**

Modify `core/models.py` (в `class Submission` рядом с `primary_score`/`ai_last_verify_at`):

```python
tutor_primary_score = models.IntegerField(null=True, blank=True, verbose_name="Итог репетитора (первичный балл)")
tutor_scored_at = models.DateTimeField(null=True, blank=True, verbose_name="Когда репетитор выставил итог")
```

Create migration `core/migrations/0051_submission_tutor_score_fields.py`:

```python
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0050_update_ege_physics_2026_tasktype_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="tutor_primary_score",
            field=models.IntegerField(blank=True, null=True, verbose_name="Итог репетитора (первичный балл)"),
        ),
        migrations.AddField(
            model_name="submission",
            name="tutor_scored_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Когда репетитор выставил итог"),
        ),
    ]
```

- [ ] **Step 4: GREEN — обновить `record_task_log` для приоритета репетитора**

Modify `core/analytics.py` in `record_task_log`:

```python
score = 0.0
if submission and submission.is_correct:
    score = float(task.exam_points)
elif submission:
    if submission.tutor_primary_score is not None:
        score = float(submission.tutor_primary_score)
    elif submission.primary_score:
        score = float(submission.primary_score)
```

- [ ] **Step 5: Run tests**

Run:
```bash
python manage.py test core.tests.test_tutor_override_score_affects_analytics -v 1
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/models.py core/analytics.py core/migrations/0051_submission_tutor_score_fields.py core/tests/test_tutor_override_score_affects_analytics.py
git commit -m "feat: add tutor score fields on submissions"
```

---

### Task 2: API — репетитор выставляет итоговый балл (только 2 часть)

**Files:**
- Modify: `core/views.py`
- Modify: `core/urls.py`
- Test: `core/tests/test_tutor_override_score_api.py`

- [ ] **Step 1: RED — тест на endpoint выставления балла**

Create `core/tests/test_tutor_override_score_api.py`:

```python
from django.test import TestCase
from django.urls import reverse
from core.models import Subject, Topic, ExamFormat, TaskType, Task, User, Assignment, Submission


class TutorOverrideScoreApiTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor.students.add(self.student)

        subj = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subj, name="T")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=22, name="22", max_points=2)
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=ef)
        self.assignment.tasks.add(self.task)

        self.sub = Submission.objects.create(student=self.student, task=self.task, assignment=self.assignment, image_url="submissions/x.png", primary_score=1)

    def test_tutor_can_override_score(self):
        self.client.login(username="t", password="pass")
        url = reverse("api_tutor_override_score", args=[self.sub.id])
        r = self.client.post(url, data={"tutor_primary_score": "2"})
        self.assertEqual(r.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.tutor_primary_score, 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python manage.py test core.tests.test_tutor_override_score_api -v 1
```
Expected: FAIL (url/view missing).

- [ ] **Step 3: GREEN — добавить view**

In `core/views.py` add:

```python
from django.views.decorators.http import require_POST
from django.utils import timezone


@login_required
@require_POST
def api_tutor_override_score(request, submission_id):
    if request.user.role != "tutor":
        return JsonResponse({"error": "forbidden"}, status=403)
    submission = get_object_or_404(Submission.objects.select_related("assignment", "student", "task", "task__task_type"), id=submission_id)

    # Права: репетитор этого варианта или репетитор этого ученика
    if submission.assignment_id:
        if submission.assignment.tutor_id != request.user.id:
            return JsonResponse({"error": "forbidden"}, status=403)
    else:
        if not request.user.students.filter(id=submission.student_id).exists():
            return JsonResponse({"error": "forbidden"}, status=403)

    # Только 2 часть
    if not is_extended_answer_task(submission.task):
        return JsonResponse({"error": "only_second_part"}, status=400)

    raw = (request.POST.get("tutor_primary_score") or "").strip()
    if not raw.lstrip("-").isdigit():
        return JsonResponse({"error": "bad_score"}, status=400)
    val = int(raw)
    max_points = max(int(submission.task.exam_points or 0), int(getattr(submission.task.task_type, "max_points", 0) or 0))
    if val < 0 or val > max_points:
        return JsonResponse({"error": "out_of_range"}, status=400)

    submission.tutor_primary_score = val
    submission.tutor_scored_at = timezone.now()
    submission.save(update_fields=["tutor_primary_score", "tutor_scored_at"])
    return JsonResponse({"status": "ok", "tutor_primary_score": submission.tutor_primary_score})
```

- [ ] **Step 4: GREEN — добавить URL**

In `core/urls.py`:

```python
path("api/tutor/submission/<int:submission_id>/override-score/", views.api_tutor_override_score, name="api_tutor_override_score"),
```

- [ ] **Step 5: Run tests**

```bash
python manage.py test core.tests.test_tutor_override_score_api -v 1
```

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/urls.py core/tests/test_tutor_override_score_api.py
git commit -m "feat: tutor override score api"
```

---

### Task 3: API — перепроверка ИИ репетитором (кулдаун 2 минуты)

**Files:**
- Modify: `core/views.py`
- Modify: `core/urls.py`
- Test: `core/tests/test_tutor_verify_ai_cooldown_and_permissions.py`

- [ ] **Step 1: RED — тест на cooldown и права**

Create `core/tests/test_tutor_verify_ai_cooldown_and_permissions.py`:

```python
import json
import os
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from core.models import Subject, Topic, ExamFormat, TaskType, Task, User, Assignment, Submission, SubjectAIConfig, OpenRouterModel


class TutorVerifyAiCooldownTests(TestCase):
    def setUp(self):
        os.environ["OPENROUTER_API_KEY"] = "test"
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.tutor.students.add(self.student)

        subj = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subj, name="T")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)

        model = OpenRouterModel.objects.create(code="test-model", name="Test", is_active=True)
        SubjectAIConfig.objects.create(subject=subj, photo_analysis_model=model)

        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="A", is_draft=False, exam_format=ef)
        self.assignment.tasks.add(self.task)
        self.sub = Submission.objects.create(student=self.student, task=self.task, assignment=self.assignment, image_url="submissions/x.png")

    def test_tutor_verify_ai_has_cooldown(self):
        self.client.login(username="t", password="pass")
        url = reverse("api_tutor_verify_with_ai", args=[self.sub.id])

        from unittest.mock import patch
        dummy_response = {"choices": [{"message": {"content": json.dumps({"primary_score": 1, "is_correct": False, "feedback": "ok"})}}]}
        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response

            r1 = self.client.post(url)
            self.assertEqual(r1.status_code, 200)
            r2 = self.client.post(url)
            self.assertEqual(r2.status_code, 429)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test core.tests.test_tutor_verify_ai_cooldown_and_permissions -v 1
```

- [ ] **Step 3: GREEN — добавить endpoint, переиспользовав логику студента**

Подход: вынести общий helper:
`_verify_submission_with_ai(request, submission, *, allow_roles)` который возвращает `JsonResponse`.

Минимальная реализация (в `core/views.py`):
1) Вынести внутренности `api_verify_with_ai` в helper, параметризовав проверку прав и выбор submission.
2) Оставить существующий `api_verify_with_ai` (student) как thin-wrapper.
3) Добавить `api_tutor_verify_with_ai`:

```python
@login_required
def api_tutor_verify_with_ai(request, submission_id):
    if request.method != "POST":
        return JsonResponse({"error": "bad_method"}, status=405)
    if request.user.role != "tutor":
        return JsonResponse({"error": "forbidden"}, status=403)
    submission = get_object_or_404(Submission.objects.select_related("assignment", "task", "task__topic"), id=submission_id)
    if submission.assignment_id and submission.assignment.tutor_id != request.user.id:
        return JsonResponse({"error": "forbidden"}, status=403)
    return _verify_submission_with_ai(request, submission)
```

**Важно:** кулдаун остаётся по `submission.ai_last_verify_at` (уже реализован в текущем коде).

- [ ] **Step 4: URL**

`core/urls.py`:
```python
path("api/tutor/submission/<int:submission_id>/verify-ai/", views.api_tutor_verify_with_ai, name="api_tutor_verify_with_ai"),
```

- [ ] **Step 5: Run tests**

```bash
python manage.py test core.tests.test_tutor_verify_ai_cooldown_and_permissions -v 1
```

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/urls.py core/tests/test_tutor_verify_ai_cooldown_and_permissions.py
git commit -m "feat: tutor ai verify endpoint with cooldown"
```

---

### Task 4: UI репетитора — фото решения, вердикт ИИ, итог репетитора, перепроверка

**Files:**
- Modify: `core/templates/core/tutor_assignment_view.html`
- (optional) Modify: `core/views.py` (добавить вычисление retry_after для репетитора аналогично student_solve_assignment)
- Test: `core/tests/test_tutor_assignment_view_shows_ai_and_photo.py`

- [ ] **Step 1: RED — тест что страница показывает блоки**

Create `core/tests/test_tutor_assignment_view_shows_ai_and_photo.py`:

```python
from django.test import TestCase
from django.urls import reverse
from core.models import Subject, Topic, ExamFormat, TaskType, Task, User, Assignment, Submission


class TutorAssignmentViewShowsAiAndPhotoTests(TestCase):
    def test_page_renders_ai_block_when_feedback_present(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)
        subj = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subj, name="T")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=21, name="21", max_points=3, is_extended_answer=True)
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=3)
        a = Assignment.objects.create(tutor=tutor, student=student, title="A", is_draft=False, exam_format=ef)
        a.tasks.add(task)
        Submission.objects.create(student=student, task=task, assignment=a, ai_feedback="ok", primary_score=2)

        self.client.login(username="t", password="pass")
        r = self.client.get(reverse("tutor_assignment_view", args=[a.id]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode("utf-8")
        self.assertIn("Вердикт ИИ", html)
        self.assertIn("Оценено:", html)
        self.assertIn("Итог репетитора", html)
```

- [ ] **Step 2: Run test (expect fail)**

```bash
python manage.py test core.tests.test_tutor_assignment_view_shows_ai_and_photo -v 1
```

- [ ] **Step 3: GREEN — обновить шаблон**

В `tutor_assignment_view.html` внутри блока `Ответ ученика` добавить:
- если `item.submission.image_url` — показать миниатюру + клик для lightbox;
- если `item.submission.ai_feedback` — показать блок “Вердикт ИИ” (аналог student_solve_assignment);
- добавить поле для `tutor_primary_score` + “Сохранить” (fetch на `override-score`);
- добавить кнопку “Перепроверить ИИ” (fetch на `verify-ai`) + таймер кулдауна по `ai_last_verify_at` (можно вычислять на сервере, либо после 429 показывать таймер).

Ключевые JS-вызовы:
- `POST /api/tutor/submission/<id>/override-score/`
- `POST /api/tutor/submission/<id>/verify-ai/`

- [ ] **Step 4: Run tests**

```bash
python manage.py test core.tests.test_tutor_assignment_view_shows_ai_and_photo -v 1
```

- [ ] **Step 5: Commit**

```bash
git add core/templates/core/tutor_assignment_view.html core/tests/test_tutor_assignment_view_shows_ai_and_photo.py
git commit -m "feat: tutor assignment view shows ai feedback and override"
```

---

### Task 5: Deep-link комментариев: из карточки ученика к конкретной задаче

**Files:**
- Modify: `core/views.py` (tutor_dashboard: `latest_unread_submission_id`)
- Modify: `core/templates/core/tutor_dashboard.html` (ссылка `?submission_id=...`)
- Modify: `core/templates/core/tutor_student_history.html` (автораскрытие/скролл)
- Test: `core/tests/test_tutor_dashboard_unread_link_points_to_submission.py`

- [ ] **Step 1: RED — тест на наличие параметра submission_id в ссылке**

Create `core/tests/test_tutor_dashboard_unread_link_points_to_submission.py`:

```python
from django.test import TestCase
from django.urls import reverse
from core.models import Subject, Topic, ExamFormat, TaskType, Task, User, Assignment, Submission, SubmissionComment


class TutorDashboardUnreadLinkTests(TestCase):
    def test_unread_questions_link_contains_submission_id(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)
        subj = Subject.objects.create(name="Физика")
        topic = Topic.objects.create(subject=subj, name="T")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1)
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        a = Assignment.objects.create(tutor=tutor, student=student, title="A", is_draft=False, exam_format=ef)
        a.tasks.add(task)
        sub = Submission.objects.create(student=student, task=task, assignment=a)
        SubmissionComment.objects.create(submission=sub, author=student, author_role="student", text="?",)

        self.client.login(username="t", password="pass")
        r = self.client.get(reverse("tutor_dashboard") + f"?student_id={student.id}")
        html = r.content.decode("utf-8")
        self.assertIn(f"submission_id={sub.id}", html)
```

- [ ] **Step 2: Run test (expect fail)**

```bash
python manage.py test core.tests.test_tutor_dashboard_unread_link_points_to_submission -v 1
```

- [ ] **Step 3: GREEN — вычислить `latest_unread_submission_id` на tutor_dashboard**

В `core/views.py` добавить subquery (похожий на `unresolved_qs`), но возвращающий `submission_id`:

```python
latest_unread_submission_qs = (
    SubmissionComment.objects.filter(
        submission__student_id=OuterRef("pk"),
        author_role="student",
        seen_by_tutor_at__isnull=True,
        submission__assignment__tutor=request.user,
    )
    .order_by("-created_at")
    .values("submission_id")[:1]
)
...
students = students.annotate(
    latest_unread_submission_id=Subquery(latest_unread_submission_qs, output_field=IntegerField())
)
```

- [ ] **Step 4: GREEN — изменить ссылку в `tutor_dashboard.html`**

Заменить:
```html
<a href="{% url 'tutor_student_history' student.id %}" ...>
```
на:
```html
<a href="{% url 'tutor_student_history' student.id %}{% if student.latest_unread_submission_id %}?submission_id={{ student.latest_unread_submission_id }}{% endif %}" ...>
```

- [ ] **Step 5: GREEN — авто-раскрытие/скролл в `tutor_student_history.html`**

Добавить JS:
- `const sid = new URLSearchParams(location.search).get("submission_id")`
- раскрыть первый day accordion содержащий `#task_<sid>` или `#prac_task_<sid>`
- вызвать `toggleTaskDetail(...)`
- `scrollIntoView({behavior:"smooth", block:"center"})` + временная подсветка рамкой.

- [ ] **Step 6: Run tests**

```bash
python manage.py test core.tests.test_tutor_dashboard_unread_link_points_to_submission -v 1
```

- [ ] **Step 7: Commit**

```bash
git add core/views.py core/templates/core/tutor_dashboard.html core/templates/core/tutor_student_history.html core/tests/test_tutor_dashboard_unread_link_points_to_submission.py
git commit -m "feat: deep link to submission from tutor dashboard"
```

---

### Task 6: Live-обновление вариантов на дашборде ученика (без refresh)

**Files:**
- Modify: `core/views.py`
- Modify: `core/urls.py`
- Modify: `core/templates/core/student_dashboard.html`
- Test: `core/tests/test_student_pending_assignments_api.py`

- [ ] **Step 1: RED — тест на API pending assignments**

Create `core/tests/test_student_pending_assignments_api.py`:

```python
from django.test import TestCase
from django.urls import reverse
from core.models import Subject, Topic, ExamFormat, TaskType, Task, User, Assignment, StudentSubjectProfile


class StudentPendingAssignmentsApiTests(TestCase):
    def test_api_returns_pending_assignments(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        subj = Subject.objects.create(name="Физика")
        StudentSubjectProfile.objects.create(student=student, subject=subj)
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ физика", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subj, name="T")
        tt = TaskType.objects.create(exam_format=ef, number=1, name="1", max_points=1)
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        a = Assignment.objects.create(tutor=tutor, student=student, title="A", is_draft=False, is_completed=False, exam_format=ef)
        a.tasks.add(task)

        self.client.login(username="s", password="pass")
        r = self.client.get(reverse("api_student_pending_assignments"))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(any(x.get("id") == a.id for x in data.get("assignments", [])))
```

- [ ] **Step 2: Run test (expect fail)**

```bash
python manage.py test core.tests.test_student_pending_assignments_api -v 1
```

- [ ] **Step 3: GREEN — добавить endpoint**

В `core/views.py`:

```python
@login_required
def api_student_pending_assignments(request):
    if request.user.role != "student":
        return JsonResponse({"error": "forbidden"}, status=403)
    qs = Assignment.objects.filter(student=request.user, is_draft=False, is_completed=False).order_by("-created_at")[:50]
    items = []
    for a in qs:
        items.append({
            "id": a.id,
            "title": a.title,
            "due_date": a.due_date.isoformat() if a.due_date else None,
            "is_verified": bool(a.is_verified),
            "tasks_count": a.tasks.count(),
        })
    return JsonResponse({"assignments": items})
```

`core/urls.py`:
```python
path("api/student/pending-assignments/", views.api_student_pending_assignments, name="api_student_pending_assignments"),
```

- [ ] **Step 4: GREEN — polling в `student_dashboard.html`**

Добавить JS:
- `setInterval` 10–15 сек
- `document.visibilityState === "visible"`
- fetch endpoint, сравнить список id, если изменился — перерендерить только блок (минимальный шаблон строк).

- [ ] **Step 5: Run tests**

```bash
python manage.py test core.tests.test_student_pending_assignments_api -v 1
```

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/urls.py core/templates/core/student_dashboard.html core/tests/test_student_pending_assignments_api.py
git commit -m "feat: student dashboard polls pending assignments"
```

---

### Task 7: Полный прогон тестов и деплой

- [ ] **Step 1: Run full test suite**

```bash
python manage.py test core.tests -v 1
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

- [ ] **Step 3: VPS**

```bash
cd /var/www/system_kazakov && git pull
python manage.py migrate
sudo systemctl restart examprep.service
```

---

## Self-review (spec coverage)

- Фото решения + вердикт ИИ у репетитора: Task 4  
- Правка баллов, влияет на аналитику: Tasks 1–2  
- Перегенерация ИИ у репетитора + кулдаун: Task 3–4  
- Переход по комментарию к конкретной задаче: Task 5  
- Варианты репетитора появляются у ученика без refresh: Task 6  

