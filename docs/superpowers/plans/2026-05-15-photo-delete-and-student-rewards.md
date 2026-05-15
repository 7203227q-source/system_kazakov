# Photo delete + student rewards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить ученику возможность удалить прикреплённое фото решения (со сбросом ИИ-вердикта) и показать ученику список наград XP от репетитора с текстом причины на дашборде ученика.

**Architecture:** 1) Добавляем новый защищённый endpoint `api_submission_clear_images`, который очищает поля `image_url/image_url_2` и ИИ-поля у `Submission`. 2) В `student_solve_assignment.html` добавляем кнопку «Удалить фото», которая вызывает endpoint и обновляет UI. 3) В `student_dashboard` подтягиваем `TutorReward` для текущего ученика и показываем блок «Награды от репетитора».

**Tech Stack:** Django 6, Django templates, vanilla JS.

---

## Map of changes (files)

**Modify:**
- `core/views.py`:
  - добавить endpoint `api_submission_clear_images`
  - добавить загрузку наград `TutorReward` в `student_dashboard`
- `core/urls.py` — добавить маршрут для `api_submission_clear_images`
- `core/templates/core/student_solve_assignment.html` — кнопка «Удалить фото» и JS-вызов очистки
- `core/templates/core/student_dashboard.html` — новый блок «Награды от репетитора»

**Create:**
- `core/tests/test_submission_clear_images.py`
- `core/tests/test_student_dashboard_rewards.py`

---

## Task 1: Endpoint очистки фото + тесты

**Files:**
- Create: `core/tests/test_submission_clear_images.py`
- Modify: `core/views.py`
- Modify: `core/urls.py`

- [ ] **Step 1: Write failing test for clear-images (owner can clear)**

Create `core/tests/test_submission_clear_images.py`:

```python
import base64

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User, Submission


class SubmissionClearImagesTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        self.task_type = TaskType.objects.create(exam_format=self.exam_format, number=20, name="Тип 20", max_points=2, is_extended_answer=True)
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")
        self.task = Task.objects.create(fipi_id="X1", topic=self.topic, task_type=self.task_type, correct_answer="1", difficulty=10, exam_points=2)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        self.student = User.objects.create_user(username="st1", password="pw", role="student")
        self.other = User.objects.create_user(username="st2", password="pw", role="student")

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        image2 = SimpleUploadedFile("b.png", png_bytes, content_type="image/png")
        self.submission = Submission.objects.create(
            student=self.student,
            task=self.task,
            image_url=image,
            image_url_2=image2,
            ai_feedback="old",
            ai_recognized_solution="sol",
            ai_mistakes_json='["m"]',
            ai_verdict_json='["v"]',
            primary_score=1,
            is_correct=False,
        )

    def test_owner_can_clear_images_and_ai_fields(self):
        self.client.force_login(self.student)
        res = self.client.post(reverse("api_submission_clear_images", args=[self.submission.id]))
        self.assertEqual(res.status_code, 200)

        self.submission.refresh_from_db()
        self.assertFalse(bool(self.submission.image_url))
        self.assertFalse(bool(getattr(self.submission, "image_url_2", None)))
        self.assertIsNone(self.submission.ai_feedback)
        self.assertIsNone(self.submission.ai_recognized_solution)
        self.assertIsNone(self.submission.ai_mistakes_json)
        self.assertIsNone(self.submission.ai_verdict_json)
        self.assertEqual(self.submission.primary_score, 0)
        self.assertFalse(self.submission.is_correct)

    def test_other_student_forbidden(self):
        self.client.force_login(self.other)
        res = self.client.post(reverse("api_submission_clear_images", args=[self.submission.id]))
        self.assertEqual(res.status_code, 403)
```

- [ ] **Step 2: Run test to verify RED**

Run:
```bash
python manage.py test core.tests.test_submission_clear_images
```
Expected: FAIL (no url/view).

- [ ] **Step 3: Implement endpoint in `core/views.py`**

Add:

```python
from django.views.decorators.http import require_POST


@login_required
@require_POST
def api_submission_clear_images(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id, student=request.user)

    # Очистка изображений
    submission.image_url = None
    if hasattr(submission, "image_url_2"):
        submission.image_url_2 = None

    # Сброс ИИ-вердикта и оценки
    submission.ai_feedback = None
    submission.ai_recognized_solution = None
    submission.ai_mistakes_json = None
    submission.ai_verdict_json = None
    submission.primary_score = 0
    submission.is_correct = False

    submission.save(
        update_fields=[
            "image_url",
            "image_url_2",
            "ai_feedback",
            "ai_recognized_solution",
            "ai_mistakes_json",
            "ai_verdict_json",
            "primary_score",
            "is_correct",
        ]
    )
    return JsonResponse({"status": "ok"})
```

Note: если поле `image_url_2` точно есть — можно не проверять `hasattr`, но оставляем защиту на случай миграций/несовпадений.

- [ ] **Step 4: Wire URL in `core/urls.py`**

Add:
```python
path("api/submission/<int:submission_id>/clear-images/", views.api_submission_clear_images, name="api_submission_clear_images"),
```

- [ ] **Step 5: Run test to verify GREEN**

Run:
```bash
python manage.py test core.tests.test_submission_clear_images
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/urls.py core/tests/test_submission_clear_images.py
git commit -m "feat(submission): allow student to clear uploaded photos"
```

---

## Task 2: UI-кнопка «Удалить фото» на странице решения варианта

**Files:**
- Modify: `core/templates/core/student_solve_assignment.html`

- [ ] **Step 1: Add button in uploaded-photo block**

В блоке где `task.saved_submission.image_url` (после кнопки «Заменить/Добавить 2-ю страницу») добавить:

```html
<button
  type="button"
  onclick="clearUploadedPhotos({{ task.saved_submission.id }}, {{ task.id }})"
  class="text-xs bg-red-50 text-red-700 hover:bg-red-100 px-4 py-2 rounded-lg transition font-bold"
>
  <i class="fas fa-trash mr-2"></i> Удалить фото
</button>
```

- [ ] **Step 2: Add JS function**

В `<script>` страницы добавить:

```js
async function clearUploadedPhotos(submissionId, taskId) {
  if (!confirm('Удалить прикреплённые фото и сбросить проверку ИИ?')) return;
  try {
    const res = await fetch(`/api/submission/${submissionId}/clear-images/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': '{{ csrf_token }}' }
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error((data && data.error) ? data.error : 'clear_failed');
    location.reload();
  } catch (e) {
    alert('Не удалось удалить фото. Попробуйте ещё раз.');
  }
}
```

- [ ] **Step 3: Manual smoke-check**

Run server and verify:
1) загрузили фото → видим кнопку «Удалить фото»
2) удалили → фото исчезло, кнопка проверки ИИ пропала/сбросилась, можно загрузить заново

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/student_solve_assignment.html
git commit -m "feat(ui): add delete photo button for student"
```

---

## Task 3: Показ наград XP ученику на student dashboard

**Files:**
- Create: `core/tests/test_student_dashboard_rewards.py`
- Modify: `core/views.py` (`student_dashboard`)
- Modify: `core/templates/core/student_dashboard.html`

- [ ] **Step 1: Write failing test for rewards visibility**

Create `core/tests/test_student_dashboard_rewards.py`:

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Subject, User, StudentSubjectProfile, TutorReward


class StudentDashboardRewardsTests(TestCase):
    def test_student_sees_own_rewards_with_reason(self):
        subject = Subject.objects.create(name="Математика")
        tutor = User.objects.create_user(username="t1", password="pw", role="tutor")
        student = User.objects.create_user(username="s1", password="pw", role="student")
        other_student = User.objects.create_user(username="s2", password="pw", role="student")

        StudentSubjectProfile.objects.create(student=student, subject=subject, xp=0, level=1)
        StudentSubjectProfile.objects.create(student=other_student, subject=subject, xp=0, level=1)

        TutorReward.objects.create(tutor=tutor, student=student, subject=subject, xp_amount=50, reason="Молодец")
        TutorReward.objects.create(tutor=tutor, student=other_student, subject=subject, xp_amount=10, reason="Не показывать")

        self.client.force_login(student)
        res = self.client.get(reverse("student_dashboard"))

        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Награды от репетитора")
        self.assertContains(res, "+50 XP")
        self.assertContains(res, "Молодец")
        self.assertNotContains(res, "Не показывать")
```

- [ ] **Step 2: Run test to verify RED**

Run:
```bash
python manage.py test core.tests.test_student_dashboard_rewards
```
Expected: FAIL (block not present).

- [ ] **Step 3: Add query in `student_dashboard`**

В `core/views.py` внутри `student_dashboard` добавить:

```python
from core.models import TutorReward

recent_rewards = (
    TutorReward.objects.filter(student=request.user)
    .select_related("subject", "tutor")
    .order_by("-created_at")[:10]
)
```

И передать в context: `'recent_rewards': recent_rewards`.

- [ ] **Step 4: Render block in `student_dashboard.html`**

Добавить секцию:

```django
{% if recent_rewards %}
  <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
    <h3 class="text-sm font-bold text-gray-800 uppercase tracking-wider mb-4">
      <i class="fas fa-star text-primary mr-2"></i> Награды от репетитора
    </h3>
    <div class="space-y-2">
      {% for r in recent_rewards %}
        <div class="flex items-start justify-between gap-3 p-3 bg-gray-50 rounded-lg border border-gray-100">
          <div class="min-w-0">
            <div class="font-bold text-gray-800">+{{ r.xp_amount }} XP · {{ r.subject.name }}</div>
            {% if r.reason %}<div class="text-sm text-gray-600 whitespace-pre-wrap mt-1">{{ r.reason }}</div>{% endif %}
            <div class="text-xs text-gray-400 mt-1">От: {{ r.tutor.get_full_name|default:r.tutor.username }}</div>
          </div>
          <div class="text-xs text-gray-400 shrink-0">{{ r.created_at|date:"d.m H:i" }}</div>
        </div>
      {% endfor %}
    </div>
  </div>
{% endif %}
```

- [ ] **Step 5: Run test to verify GREEN**

Run:
```bash
python manage.py test core.tests.test_student_dashboard_rewards
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/templates/core/student_dashboard.html core/tests/test_student_dashboard_rewards.py
git commit -m "feat(student): show tutor XP rewards and reasons on dashboard"
```

---

## Task 4: Regression + push

**Files:** N/A

- [ ] **Step 1: Run core tests**

Run:
```bash
python manage.py test core.tests
```
Expected: `OK`.

- [ ] **Step 2: Push**

```bash
git push origin main
```

---

## Coverage self-check (against spec)
- Удаление фото только учеником + сброс ИИ-вердикта — Task 1 + Task 2
- Reason от наград виден ученику на дашборде — Task 3
- Тесты для обоих изменений — Task 1/3

