# Student Exam Date + Tutor SRS Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить настройку текущего формата и даты экзамена для ученика (по предмету) и дать репетитору возможность удалять задачи из интервального повторения.

**Architecture:** Экзамен хранится на уровне `StudentSubjectProfile` (по предмету): `exam_format` уже есть, добавляем `exam_date`. UI: ученик меняет дату на своём дашборде, репетитор — в карточке ученика на своём дашборде. Прогноз `DailySnapshot.predicted_exam_score` начинает учитывать `exam_date`. Удаление из SRS — отдельный POST эндпоинт репетитора, который удаляет запись `SpacedRepetition`.

**Tech Stack:** Django, Django templates (Tailwind), existing analytics in `core/analytics.py`, tests via `python manage.py test`.

---

## File Map

**Modify**
- `core/models.py` — добавить `exam_date` в `StudentSubjectProfile`
- `core/views.py` — добавить 2 POST эндпоинта: student exam date update + tutor exam settings update + tutor SRS remove; расширить `tutor_dashboard` контекст
- `core/urls.py` — добавить маршруты для новых эндпоинтов
- `core/analytics.py` — прогноз с учётом `exam_date`
- `core/templates/core/student_dashboard.html` — поле даты экзамена
- `core/templates/core/tutor_dashboard.html` — блок “Экзамен” для выбранного ученика
- `core/templates/core/tutor_student_history.html` — кнопка “Убрать из повторения”

**Create**
- `core/migrations/00xx_student_profile_exam_date.py` — миграция поля `exam_date` (номер миграции определить автоматически)
- `core/tests/test_student_exam_date.py`
- `core/tests/test_tutor_student_exam_settings.py`
- `core/tests/test_tutor_srs_remove.py`
- `core/tests/test_exam_date_forecast.py`

---

### Task 1: Add exam_date to StudentSubjectProfile

**Files:**
- Modify: `core/models.py` (class `StudentSubjectProfile`)
- Create: `core/migrations/00xx_student_profile_exam_date.py`

- [ ] **Step 1: Write failing test for model field presence**

Create `core/tests/test_student_exam_date.py`:

```python
from django.test import TestCase

from core.models import StudentSubjectProfile, Subject, User


class StudentExamDateModelTests(TestCase):
    def test_profile_has_exam_date(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        p = StudentSubjectProfile.objects.create(student=student, subject=subject, target_score=80, level=1, xp=0)
        self.assertTrue(hasattr(p, "exam_date"))
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python manage.py test core.tests.test_student_exam_date -v 1
```

Expected: FAIL (`hasattr(..., "exam_date")` is False).

- [ ] **Step 3: Add model field**

In `core/models.py` inside `StudentSubjectProfile` add:

```python
exam_date = models.DateField(null=True, blank=True, verbose_name="Дата экзамена")
```

- [ ] **Step 4: Create and apply migration (locally)**

Run:

```bash
python manage.py makemigrations core
python manage.py migrate
```

- [ ] **Step 5: Re-run the test**

Run:

```bash
python manage.py test core.tests.test_student_exam_date -v 1
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/models.py core/migrations core/tests/test_student_exam_date.py
git commit -m "feat: add exam date to student subject profile"
```

---

### Task 2: Student can set exam_date per subject from student_dashboard

**Files:**
- Modify: `core/views.py` (add endpoint)
- Modify: `core/urls.py` (route)
- Modify: `core/templates/core/student_dashboard.html` (date input)
- Test: `core/tests/test_student_exam_date.py` (extend)

- [ ] **Step 1: Write failing endpoint test**

Append to `core/tests/test_student_exam_date.py`:

```python
import datetime
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat


class StudentExamDateEndpointTests(TestCase):
    def test_student_can_update_exam_date(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        fmt = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=True)
        p = StudentSubjectProfile.objects.create(student=student, subject=subject, target_score=80, level=1, xp=0, exam_format=fmt)

        self.client.login(username="s", password="pass")
        exam_date = (timezone.now().date() + datetime.timedelta(days=30)).isoformat()
        res = self.client.post(
            reverse("student_update_exam_date"),
            {"subject_id": str(subject.id), "exam_date": exam_date},
        )
        self.assertEqual(res.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.exam_date.isoformat(), exam_date)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test core.tests.test_student_exam_date -v 1
```

Expected: FAIL (NoReverseMatch: `student_update_exam_date` not found).

- [ ] **Step 3: Add view**

Add in `core/views.py` рядом с `student_update_exam_format`:

```python
@login_required
@require_POST
def student_update_exam_date(request):
    if request.user.role != "student":
        return redirect("login")

    subject_id_raw = (request.POST.get("subject_id") or "").strip()
    exam_date_raw = (request.POST.get("exam_date") or "").strip()
    if not subject_id_raw.isdigit():
        return redirect(request.META.get("HTTP_REFERER", "student_dashboard"))

    subject_id = int(subject_id_raw)
    profile = StudentSubjectProfile.objects.filter(student=request.user, subject_id=subject_id).first()
    if profile is None:
        return redirect(request.META.get("HTTP_REFERER", "student_dashboard"))

    if not exam_date_raw:
        profile.exam_date = None
        profile.save(update_fields=["exam_date"])
        return redirect(request.META.get("HTTP_REFERER", "student_dashboard"))

    try:
        profile.exam_date = datetime.date.fromisoformat(exam_date_raw)
    except Exception:
        return redirect(request.META.get("HTTP_REFERER", "student_dashboard"))

    profile.save(update_fields=["exam_date"])
    return redirect(request.META.get("HTTP_REFERER", "student_dashboard"))
```

Ensure `datetime` is imported at top of `views.py` if not present in that section.

- [ ] **Step 4: Add URL**

In `core/urls.py` add near `student_update_exam_format`:

```python
path("student/update-exam-date/", views.student_update_exam_date, name="student_update_exam_date"),
```

- [ ] **Step 5: Add UI on student dashboard**

In `core/templates/core/student_dashboard.html` рядом с форматом (в блоке “Формат:”) добавить вторую мини-форму:

```html
<form method="POST" action="{% url 'student_update_exam_date' %}" class="flex items-center gap-2">
    {% csrf_token %}
    <input type="hidden" name="subject_id" value="{{ active_profile.subject.id }}">
    <span class="text-gray-500">Дата:</span>
    <input
        type="date"
        name="exam_date"
        value="{% if active_profile.exam_date %}{{ active_profile.exam_date|date:'Y-m-d' }}{% endif %}"
        onchange="this.form.submit()"
        class="bg-white border border-gray-200 rounded px-2 py-0.5 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-primary"
    >
</form>
```

- [ ] **Step 6: Run test to verify it passes**

```bash
python manage.py test core.tests.test_student_exam_date -v 1
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add core/views.py core/urls.py core/templates/core/student_dashboard.html core/tests/test_student_exam_date.py
git commit -m "feat: allow student to set exam date per subject"
```

---

### Task 3: Tutor can set student exam_format and exam_date per subject (default for variant generator)

**Files:**
- Modify: `core/views.py` (new endpoint + enrich tutor_dashboard context)
- Modify: `core/urls.py`
- Modify: `core/templates/core/tutor_dashboard.html`
- Test: `core/tests/test_tutor_student_exam_settings.py`

- [ ] **Step 1: Write failing test**

Create `core/tests/test_tutor_student_exam_settings.py`:

```python
import datetime
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, StudentSubjectProfile, Subject, User


class TutorStudentExamSettingsTests(TestCase):
    def test_tutor_can_update_student_exam_settings(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subject = Subject.objects.create(name="Математика")
        fmt = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=True)
        p = StudentSubjectProfile.objects.create(student=student, subject=subject, target_score=80, level=1, xp=0)

        self.client.login(username="t", password="pass")
        exam_date = (timezone.now().date() + datetime.timedelta(days=10)).isoformat()
        res = self.client.post(
            reverse("tutor_update_student_exam_settings", args=[student.id]),
            {"subject_id": str(subject.id), "exam_format_id": str(fmt.id), "exam_date": exam_date},
        )
        self.assertEqual(res.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.exam_format_id, fmt.id)
        self.assertEqual(p.exam_date.isoformat(), exam_date)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test core.tests.test_tutor_student_exam_settings -v 1
```

Expected: FAIL (NoReverseMatch).

- [ ] **Step 3: Add endpoint**

In `core/views.py` add:

```python
@login_required
@require_POST
def tutor_update_student_exam_settings(request, student_id):
    if request.user.role != "tutor":
        return redirect("login")

    student = request.user.students.filter(id=student_id).first()
    if student is None:
        messages.error(request, "Ученик не найден в вашем списке.")
        return redirect("tutor_dashboard")

    subject_id_raw = (request.POST.get("subject_id") or "").strip()
    exam_format_id_raw = (request.POST.get("exam_format_id") or "").strip()
    exam_date_raw = (request.POST.get("exam_date") or "").strip()

    if not subject_id_raw.isdigit():
        return redirect(f"{reverse('tutor_dashboard')}?student_id={student.id}")
    subject_id = int(subject_id_raw)

    profile, _ = StudentSubjectProfile.objects.get_or_create(
        student=student,
        subject_id=subject_id,
        defaults={"target_score": 80, "level": 1, "xp": 0},
    )

    if exam_format_id_raw and exam_format_id_raw.isdigit():
        exam_format = ExamFormat.objects.filter(id=int(exam_format_id_raw), subject_id=subject_id).first()
        if exam_format is not None:
            profile.exam_format = exam_format
            profile.save(update_fields=["exam_format"])

    if not exam_date_raw:
        if profile.exam_date is not None:
            profile.exam_date = None
            profile.save(update_fields=["exam_date"])
        return redirect(f"{reverse('tutor_dashboard')}?student_id={student.id}&subject_id={subject_id}")

    try:
        profile.exam_date = datetime.date.fromisoformat(exam_date_raw)
    except Exception:
        return redirect(f"{reverse('tutor_dashboard')}?student_id={student.id}&subject_id={subject_id}")

    profile.save(update_fields=["exam_date"])
    return redirect(f"{reverse('tutor_dashboard')}?student_id={student.id}&subject_id={subject_id}")
```

- [ ] **Step 4: Add URL**

In `core/urls.py` add:

```python
path("tutor/student/<int:student_id>/exam-settings/", views.tutor_update_student_exam_settings, name="tutor_update_student_exam_settings"),
```

- [ ] **Step 5: Enrich tutor_dashboard context with formats per subject**

In `tutor_dashboard` view, after:

```python
profiles = list(selected_student.subject_profiles.all())
```

add:

```python
for p in profiles:
    p.exam_formats_for_subject = ExamFormat.objects.filter(subject_id=p.subject_id).order_by("-is_active", "-year", "name")
```

and ensure template uses `profiles` from `selected_student.subject_profiles.all` (it already does) or pass `profiles` explicitly. Preferred: set back to selected_student by iterating `selected_student.subject_profiles.all()` in template (as now) but it won’t see attributes; so update template to loop `profiles` instead and pass `profiles` in context:

```python
context["profiles"] = profiles
```

- [ ] **Step 6: Add UI block in tutor_dashboard.html**

In выбранном ученике добавить блок:

```html
<div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
    <div class="text-sm font-bold text-gray-800 mb-4">Экзамен</div>
    <div class="space-y-3">
        {% for p in profiles %}
        <form method="POST" action="{% url 'tutor_update_student_exam_settings' selected_student.id %}" class="grid grid-cols-1 md:grid-cols-4 gap-3 items-end bg-gray-50 border border-gray-100 rounded-lg p-3">
            {% csrf_token %}
            <input type="hidden" name="subject_id" value="{{ p.subject.id }}">
            <div class="md:col-span-1">
                <div class="text-xs font-bold text-gray-600 mb-1">{{ p.subject.name }}</div>
            </div>
            <div class="md:col-span-2">
                <label class="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Формат</label>
                <select name="exam_format_id" class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white">
                    {% for f in p.exam_formats_for_subject %}
                    <option value="{{ f.id }}" {% if p.exam_format_id == f.id %}selected{% endif %}>{{ f.name }} {{ f.year }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="md:col-span-1">
                <label class="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Дата</label>
                <input type="date" name="exam_date" value="{% if p.exam_date %}{{ p.exam_date|date:'Y-m-d' }}{% endif %}" class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white">
            </div>
            <div class="md:col-span-4 flex justify-end">
                <button type="submit" class="bg-primary text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-indigo-700 transition">Сохранить</button>
            </div>
        </form>
        {% endfor %}
    </div>
</div>
```

- [ ] **Step 7: Run tests**

```bash
python manage.py test core.tests.test_tutor_student_exam_settings -v 1
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/views.py core/urls.py core/templates/core/tutor_dashboard.html core/tests/test_tutor_student_exam_settings.py
git commit -m "feat: allow tutor to set student exam format and date"
```

---

### Task 4: Forecast uses exam_date (days-until-exam trend)

**Files:**
- Modify: `core/analytics.py`
- Test: `core/tests/test_exam_date_forecast.py`

- [ ] **Step 1: Write failing test**

Create `core/tests/test_exam_date_forecast.py`:

```python
import datetime
from django.test import TestCase
from django.utils import timezone

from core.analytics import update_student_analytics
from core.models import DailySnapshot, ExamFormat, StudentSubjectProfile, Subject, Task, TaskLog, TaskType, Topic, User


class ExamDateForecastTests(TestCase):
    def test_forecast_grows_towards_exam_date_when_trend_positive(self):
        student = User.objects.create_user(username="s", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        fmt = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=True)
        profile = StudentSubjectProfile.objects.create(
            student=student,
            subject=subject,
            target_score=80,
            level=1,
            xp=0,
            exam_format=fmt,
            learning_velocity=1.0,
            trust_factor=1.0,
            exam_date=timezone.now().date() + datetime.timedelta(days=10),
        )

        base_date = timezone.now().date() - datetime.timedelta(days=10)
        DailySnapshot.objects.create(student=student, subject=subject, date=base_date, current_mastery=40.0, predicted_exam_score=40.0)
        DailySnapshot.objects.create(student=student, subject=subject, date=timezone.now().date() - datetime.timedelta(days=1), current_mastery=50.0, predicted_exam_score=50.0)

        topic = Topic.objects.create(subject=subject, name="T")
        tt = TaskType.objects.create(exam_format=fmt, number=1, name="Тип 1", max_points=1)
        task = Task.objects.create(topic=topic, task_type=tt, subtype_tag="x", correct_answer="1", difficulty=10, exam_points=1)
        TaskLog.objects.create(student=student, task=task, score=1.0, time_spent=60, is_anomaly=False)

        snap = update_student_analytics(student, subject)
        self.assertGreaterEqual(float(snap.predicted_exam_score), 50.0)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test core.tests.test_exam_date_forecast -v 1
```

Expected: FAIL (предсказание не учитывает тренд/дату, будет около `current_mastery`).

- [ ] **Step 3: Implement forecast logic**

In `core/analytics.py` inside `update_student_analytics` replace the block:

```python
predicted_score = current_mastery * profile.learning_velocity
predicted_score = max(0.0, min(100.0, predicted_score))
```

with:

```python
predicted_score = current_mastery * profile.learning_velocity

today = timezone.now().date()
exam_date = profile.exam_date
if exam_date and exam_date >= today:
    days_left = (exam_date - today).days
    if days_left > 0:
        start = today - datetime.timedelta(days=14)
        hist = list(
            DailySnapshot.objects.filter(student=student, subject=subject, date__gte=start, date__lt=today)
            .order_by("date")
            .values_list("date", "current_mastery")
        )
        if len(hist) >= 2:
            d0, m0 = hist[0]
            d1, m1 = hist[-1]
            span = max(1, (d1 - d0).days)
            slope = (float(m1 or 0.0) - float(m0 or 0.0)) / float(span)
            projected_mastery = float(current_mastery) + slope * float(days_left)
            predicted_score = projected_mastery * float(profile.learning_velocity or 1.0)

predicted_score = max(0.0, min(100.0, float(predicted_score)))
```

- [ ] **Step 4: Re-run test**

```bash
python manage.py test core.tests.test_exam_date_forecast -v 1
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/analytics.py core/tests/test_exam_date_forecast.py
git commit -m "feat: adjust score forecast using exam date"
```

---

### Task 5: Tutor can remove a task from student SRS

**Files:**
- Modify: `core/views.py`
- Modify: `core/urls.py`
- Modify: `core/templates/core/tutor_student_history.html`
- Test: `core/tests/test_tutor_srs_remove.py`

- [ ] **Step 1: Write failing test**

Create `core/tests/test_tutor_srs_remove.py`:

```python
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, Subject, Task, TaskType, Topic, User


class TutorSrsRemoveTests(TestCase):
    def test_tutor_can_remove_student_srs_item(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        tutor.students.add(student)

        subject = Subject.objects.create(name="Математика")
        fmt = ExamFormat.objects.create(subject=subject, name="ОГЭ математика", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subject, name="T")
        tt = TaskType.objects.create(exam_format=fmt, number=1, name="Тип 1", max_points=1)
        task = Task.objects.create(topic=topic, task_type=tt, subtype_tag="x", correct_answer="1", difficulty=10, exam_points=1)

        SpacedRepetition.objects.create(student=student, task=task, next_review_date=timezone.now().date())

        self.client.login(username="t", password="pass")
        res = self.client.post(reverse("tutor_student_srs_remove", args=[student.id, task.id]))
        self.assertEqual(res.status_code, 302)
        self.assertFalse(SpacedRepetition.objects.filter(student=student, task=task).exists())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test core.tests.test_tutor_srs_remove -v 1
```

Expected: FAIL (NoReverseMatch).

- [ ] **Step 3: Add view**

In `core/views.py` add:

```python
@login_required
@require_POST
def tutor_student_srs_remove(request, student_id, task_id):
    if request.user.role != "tutor":
        return redirect("login")

    student = request.user.students.filter(id=student_id).first()
    if student is None:
        messages.error(request, "Ученик не найден в вашем списке.")
        return redirect("tutor_dashboard")

    SpacedRepetition.objects.filter(student=student, task_id=task_id).delete()
    messages.success(request, "Задача убрана из повторения.")
    return redirect(request.META.get("HTTP_REFERER", reverse("tutor_student_history", args=[student.id])))
```

- [ ] **Step 4: Add URL**

In `core/urls.py` add:

```python
path("tutor/student/<int:student_id>/srs/remove/<int:task_id>/", views.tutor_student_srs_remove, name="tutor_student_srs_remove"),
```

- [ ] **Step 5: Add button in tutor_student_history.html**

Inside practice block (где показывается задача тренажёра), в детальном блоке `prac_task_{{ sub.id }}` добавить форму:

```html
<form method="POST" action="{% url 'tutor_student_srs_remove' student.id sub.task.id %}" class="not-prose mt-3" onsubmit="return confirm('Убрать задачу из повторения?');">
    {% csrf_token %}
    <button type="submit" class="bg-white border border-red-200 text-red-700 hover:bg-red-50 px-3 py-2 rounded-lg text-xs font-bold transition">
        <i class="fas fa-ban mr-2"></i> Убрать из повторения
    </button>
</form>
```

- [ ] **Step 6: Re-run test**

```bash
python manage.py test core.tests.test_tutor_srs_remove -v 1
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add core/views.py core/urls.py core/templates/core/tutor_student_history.html core/tests/test_tutor_srs_remove.py
git commit -m "feat: allow tutor to remove tasks from student spaced repetition"
```

---

### Task 6: Full regression test run

- [ ] **Step 1: Run full suite**

```bash
python manage.py test core.tests -v 1
```

Expected: PASS.

