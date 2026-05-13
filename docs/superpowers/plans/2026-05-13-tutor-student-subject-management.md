# Tutor Student Subject Management (Variant A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить репетитору в `tutor_dashboard` возможность добавлять предмет ученику и исправить построение решаемости по номерам так, чтобы она строго соответствовала `StudentSubjectProfile.exam_format` и набору `TaskType` выбранного формата.

**Architecture:** Все настройки экзамена по предмету берём из `StudentSubjectProfile`. При добавлении предмета создаём профиль и выставляем дефолтный `ExamFormat` (активный или самый новый). Решаемость по номерам строим только по `TaskType` выбранного формата (никаких захардкоженных диапазонов).

**Tech Stack:** Django views/templates, Django TestCase.

---

## Изменяемые файлы (map)

**Modify**
- `/workspace/core/views.py` — добавить endpoint для добавления предмета; починить формирование `task_type_rates` под `exam_format`.
- `/workspace/core/templates/core/tutor_dashboard.html` — добавить форму “Добавить предмет”; добавить бейдж “Формат: …” рядом с решаемостью.
- `/workspace/core/tests/test_tutor_student_exam_settings.py` — расширить тесты по экзаменным настройкам.
- `/workspace/core/tests/test_tutor_dashboard_task_type_rates.py` — новый тест на соответствие количества “номеров” количеству `TaskType` выбранного `exam_format`.

**Create**
- `/workspace/core/tests/test_tutor_add_student_subject.py` — тест на добавление предмета ученику из `tutor_dashboard`.

---

### Task 1: RED — тест на добавление предмета ученику из tutor_dashboard

**Files:**
- Create: `/workspace/core/tests/test_tutor_add_student_subject.py`

- [ ] **Step 1: Write failing test**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, StudentSubjectProfile, Subject, User


class TutorAddStudentSubjectTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        self.math = Subject.objects.create(name="Математика")
        self.phys = Subject.objects.create(name="Физика")

        self.oge_math = ExamFormat.objects.create(subject=self.math, name="ОГЭ математика", year=2026, is_active=True)
        self.ege_phys = ExamFormat.objects.create(subject=self.phys, name="ЕГЭ физика", year=2026, is_active=True)

    def test_tutor_can_add_subject_profile(self):
        self.client.login(username="t", password="pass")

        self.assertFalse(StudentSubjectProfile.objects.filter(student=self.student, subject=self.phys).exists())

        res = self.client.post(
            reverse("tutor_add_student_subject", args=[self.student.id]),
            {"subject_id": str(self.phys.id)},
        )
        self.assertEqual(res.status_code, 302)

        prof = StudentSubjectProfile.objects.get(student=self.student, subject=self.phys)
        self.assertEqual(prof.exam_format_id, self.ege_phys.id)
```

- [ ] **Step 2: Run to verify fails**

```bash
python manage.py test core.tests.test_tutor_add_student_subject -v 1
```
Expected: FAIL (url/view отсутствуют).

- [ ] **Step 3: Commit failing test**

```bash
git add core/tests/test_tutor_add_student_subject.py
git commit -m "test: add tutor add-student-subject flow"
```

---

### Task 2: GREEN — endpoint tutor_add_student_subject + wiring в urls

**Files:**
- Modify: `/workspace/core/urls.py`
- Modify: `/workspace/core/views.py`
- Test: `/workspace/core/tests/test_tutor_add_student_subject.py`

- [ ] **Step 1: Implement view**

В `core/views.py` добавить:

```python
@login_required
@require_POST
def tutor_add_student_subject(request, student_id):
    if request.user.role != "tutor":
        return redirect("login")

    student = request.user.students.filter(id=student_id).first()
    if student is None:
        return redirect("tutor_dashboard")

    subject_id_raw = (request.POST.get("subject_id") or "").strip()
    if not subject_id_raw.isdigit():
        return redirect(request.META.get("HTTP_REFERER", reverse("tutor_dashboard")))
    subject_id = int(subject_id_raw)

    default_exam_format = (
        ExamFormat.objects.filter(subject_id=subject_id, is_active=True).order_by("-year", "name").first()
        or ExamFormat.objects.filter(subject_id=subject_id).order_by("-year", "name").first()
    )

    profile, created = StudentSubjectProfile.objects.get_or_create(
        student=student,
        subject_id=subject_id,
        defaults={"target_score": 80, "level": 1, "xp": 0, "exam_format": default_exam_format},
    )
    if (not created) and profile.exam_format_id is None and default_exam_format is not None:
        profile.exam_format = default_exam_format
        profile.save(update_fields=["exam_format"])

    return redirect(f"{reverse('tutor_dashboard')}?student_id={student.id}")
```

- [ ] **Step 2: Wire URL**

В `core/urls.py` добавить рядом с другими tutor routes:

```python
path('tutor/student/<int:student_id>/add-subject/', views.tutor_add_student_subject, name='tutor_add_student_subject'),
```

- [ ] **Step 3: Run test**

```bash
python manage.py test core.tests.test_tutor_add_student_subject -v 1
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/urls.py
git commit -m "feat: tutor can add subject to student"
```

---

### Task 3: tutor_dashboard UI — форма “Добавить предмет” рядом с блоком «Экзамен»

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`
- Test: `/workspace/core/tests/test_tutor_add_student_subject.py`

- [ ] **Step 1: Provide available subjects list in context**

В `tutor_dashboard` после определения `profiles` добавить:
- `all_subjects = Subject.objects.all().order_by("name")`
- `available_subjects = [s for s in all_subjects if s.id not in {p.subject_id for p in profiles}]`
- положить `available_subjects` в `context`.

- [ ] **Step 2: Add form in template**

В `tutor_dashboard.html` в блоке «Экзамен» над списком профилей:
- select `name="subject_id"` по `available_subjects`
- `action="{% url 'tutor_add_student_subject' selected_student.id %}"`
- `method="POST"` + csrf + кнопка “Добавить предмет”

- [ ] **Step 3: Run existing tests**

```bash
python manage.py test core.tests.test_tutor_add_student_subject -v 1
```

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/templates/core/tutor_dashboard.html
git commit -m "feat: add subject picker to tutor dashboard"
```

---

### Task 4: RED — тест: решаемость по номерам соответствует TaskType выбранного exam_format

**Files:**
- Create: `/workspace/core/tests/test_tutor_dashboard_task_type_rates.py`

- [ ] **Step 1: Write failing test**

```python
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import DailySnapshot, ExamFormat, StudentSubjectProfile, Subject, TaskType, User


class TutorDashboardTaskTypeRatesTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        self.subj = Subject.objects.create(name="Математика")
        self.ef = ExamFormat.objects.create(subject=self.subj, name="ОГЭ математика", year=2026, is_active=True)
        for n in range(1, 6):
            TaskType.objects.create(exam_format=self.ef, number=n, name=f"Тип {n}", max_points=1)

        StudentSubjectProfile.objects.create(student=self.student, subject=self.subj, exam_format=self.ef)
        DailySnapshot.objects.create(student=self.student, subject=self.subj, date=timezone.localdate(), current_mastery=10, predicted_exam_score=10)

    def test_tutor_dashboard_shows_all_numbers_from_exam_format(self):
        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("tutor_dashboard"), {"student_id": self.student.id, "subject_id": self.subj.id})
        self.assertEqual(res.status_code, 200)
        # Плитки по номерам: ожидаем №1..№5
        for n in range(1, 6):
            self.assertContains(res, f">№{n}<")
```

- [ ] **Step 2: Run to verify fails**

```bash
python manage.py test core.tests.test_tutor_dashboard_task_type_rates -v 1
```
Expected: FAIL (сейчас список номеров не берется строго из TaskType выбранного формата).

- [ ] **Step 3: Commit failing test**

```bash
git add core/tests/test_tutor_dashboard_task_type_rates.py
git commit -m "test: tutor dashboard task type rates follow exam format"
```

---

### Task 5: GREEN — tutor_dashboard: task_type_rates строится по TaskType выбранного exam_format

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`
- Test: `/workspace/core/tests/test_tutor_dashboard_task_type_rates.py`

- [ ] **Step 1: Fix logic in views**

В `tutor_dashboard` заменить текущую логику `numbers = ... list(range(1, 20))` на:
- если `active_exam_format` есть: `numbers = list(TaskType.objects.filter(exam_format=active_exam_format).values_list("number", flat=True).order_by("number"))`
- иначе fallback `numbers = []`

И добавить в контекст строку формата:
- `active_exam_format_label = f"{active_exam_format.name} {active_exam_format.year}"` (если есть)

- [ ] **Step 2: Show badge in template**

В блоке с решаемостью/диаграммой добавить текст:
- `Формат: {{ active_exam_format_label }}` (если есть)

- [ ] **Step 3: Run tests**

```bash
python manage.py test core.tests.test_tutor_dashboard_task_type_rates -v 1
python manage.py test core.tests.test_tutor_add_student_subject -v 1
```

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/templates/core/tutor_dashboard.html
git commit -m "fix: tutor dashboard rates follow selected exam format"
```

---

### Task 6: Full regression

- [ ] **Step 1: Run full test suite**

```bash
python manage.py test core.tests -v 1
```

- [ ] **Step 2: Push**

```bash
git push origin HEAD:main
```

