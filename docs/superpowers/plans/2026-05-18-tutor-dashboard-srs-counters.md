# Tutor Dashboard SRS Counters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В кабинете репетитора показывать для каждого ученика “Повтор сегодня” (сколько SRS задач должно быть повторено сегодня) и “Повторил” (сколько SRS задач ученик повторил сегодня) в списке и в шапке профиля.

**Architecture:** Фиксируем факт SRS-повтора в SpacedRepetition.last_reviewed_at при каждом обновлении SM-2. В tutor_dashboard считаем агрегатами по всем ученикам мапы due/reviewed и прокидываем в шаблон через поля на объектах student.

**Tech Stack:** Django (models/migrations/views/templates), unittest через Django TestCase.

---

## Затрагиваемые файлы

- Modify: [models.py](file:///workspace/core/models.py) (SpacedRepetition: новое поле)
- Create: `/workspace/core/migrations/00xx_spacedrepetition_last_reviewed_at.py` (миграция поля)
- Modify: [services.py](file:///workspace/core/services.py) (process_srs_review: обновление last_reviewed_at)
- Modify: [views.py](file:///workspace/core/views.py) (tutor_dashboard: агрегаты due/reviewed + прокидка в objects)
- Modify: [tutor_dashboard.html](file:///workspace/core/templates/core/tutor_dashboard.html) (вывод бейджей в двух местах)
- Create: `/workspace/core/tests/test_tutor_dashboard_srs_counters.py` (тесты)

## Task 1: Тесты для last_reviewed_at и метрик tutor_dashboard

**Files:**
- Create: `/workspace/core/tests/test_tutor_dashboard_srs_counters.py`

- [ ] **Step 1: Write failing tests**

```python
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ExamFormat, SpacedRepetition, Subject, Task, TaskType, Topic, User
from core.services import process_srs_review


class TutorDashboardSrsCountersTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.student.tutors.add(self.tutor)

        subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=1, name="Тест", max_points=1)
        topic = Topic.objects.create(subject=subject, name="T")
        self.task1 = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)
        self.task2 = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=1)

    def test_process_srs_review_sets_last_reviewed_at(self):
        rec = SpacedRepetition.objects.create(
            student=self.student,
            task=self.task1,
            next_review_date=timezone.localdate(),
        )
        self.assertIsNone(getattr(rec, "last_reviewed_at", None))

        before = timezone.now()
        process_srs_review(rec, grade=5)
        rec.refresh_from_db()
        self.assertIsNotNone(rec.last_reviewed_at)
        self.assertGreaterEqual(rec.last_reviewed_at, before)

    def test_tutor_dashboard_shows_srs_due_and_reviewed_today(self):
        today = timezone.localdate()
        yesterday = today - timezone.timedelta(days=1)

        SpacedRepetition.objects.create(student=self.student, task=self.task1, next_review_date=today)
        SpacedRepetition.objects.create(student=self.student, task=self.task2, next_review_date=yesterday)

        # “Повторил сегодня” должен считать только last_reviewed_at__date==today
        SpacedRepetition.objects.filter(student=self.student, task=self.task2).update(last_reviewed_at=timezone.now())

        self.client.login(username="t", password="pass")
        r = self.client.get(reverse("tutor_dashboard"))
        self.assertEqual(r.status_code, 200)

        self.assertContains(r, "Повтор сегодня")
        self.assertContains(r, "Повторил")

        # due today: обе записи (today и просроченная)
        self.assertContains(r, "Повтор сегодня: 2")
        self.assertContains(r, "Повторил: 1")
```

- [ ] **Step 2: Run tests to confirm they fail**

Run:

```bash
pytest /workspace/core/tests/test_tutor_dashboard_srs_counters.py -q
```

Expected:
- FAIL/Error, т.к. поля last_reviewed_at ещё нет и tutor_dashboard не выводит метрики.

## Task 2: Добавить last_reviewed_at в SpacedRepetition (+ миграция)

**Files:**
- Modify: [models.py](file:///workspace/core/models.py#L266-L286)
- Create: `/workspace/core/migrations/00xx_spacedrepetition_last_reviewed_at.py`

- [ ] **Step 1: Add model field**

В SpacedRepetition добавить поле:

```python
last_reviewed_at = models.DateTimeField(null=True, blank=True, db_index=True)
```

- [ ] **Step 2: Add migration**

Создать миграцию с AddField для `last_reviewed_at` и индексом (db_index=True в модели достаточно).

- [ ] **Step 3: Run tests**

```bash
pytest /workspace/core/tests/test_tutor_dashboard_srs_counters.py::TutorDashboardSrsCountersTests::test_process_srs_review_sets_last_reviewed_at -q
```

Expected:
- Всё ещё FAIL, потому что логика обновления last_reviewed_at не реализована.

## Task 3: Обновлять last_reviewed_at при SRS-повторе

**Files:**
- Modify: [services.py](file:///workspace/core/services.py#L50-L87)

- [ ] **Step 1: Update process_srs_review**

Добавить установку `last_reviewed_at` перед `save()`:

```python
from django.utils import timezone

def process_srs_review(srs_record, grade):
    ...
    srs_record.last_grade = grade
    srs_record.last_reviewed_at = timezone.now()
    srs_record.next_review_date = timezone.now().date() + timedelta(days=srs_record.interval)
    srs_record.save()
    return srs_record
```

- [ ] **Step 2: Run the single test**

```bash
pytest /workspace/core/tests/test_tutor_dashboard_srs_counters.py::TutorDashboardSrsCountersTests::test_process_srs_review_sets_last_reviewed_at -q
```

Expected:
- PASS

## Task 4: Посчитать и прокинуть метрики в tutor_dashboard

**Files:**
- Modify: [views.py](file:///workspace/core/views.py#L2121-L2350)

- [ ] **Step 1: Add aggregated maps**

Внутри `tutor_dashboard`, после вычисления `today` и `student_ids`, добавить:

```python
from django.db.models import Count

srs_due_today_map: dict[int, int] = {}
srs_reviewed_today_map: dict[int, int] = {}
if student_ids:
    rows = (
        SpacedRepetition.objects.filter(student_id__in=student_ids, next_review_date__lte=today)
        .values("student_id")
        .annotate(c=Count("id"))
        .values_list("student_id", "c")
    )
    srs_due_today_map = {int(sid): int(c) for sid, c in rows}

    rows = (
        SpacedRepetition.objects.filter(student_id__in=student_ids, last_reviewed_at__date=today)
        .values("student_id")
        .annotate(c=Count("id"))
        .values_list("student_id", "c")
    )
    srs_reviewed_today_map = {int(sid): int(c) for sid, c in rows}
```

- [ ] **Step 2: Attach fields on student objects**

В цикле `for s in students:` добавить:

```python
s.srs_due_today = int(srs_due_today_map.get(int(s.id), 0))
s.srs_reviewed_today = int(srs_reviewed_today_map.get(int(s.id), 0))
```

И заменить `pending_srs_count` на `s.srs_due_today` (чтобы не делать лишний запрос):

```python
pending_srs_count = int(getattr(s, "srs_due_today", 0))
```

- [ ] **Step 3: Run tutor dashboard test**

```bash
pytest /workspace/core/tests/test_tutor_dashboard_srs_counters.py::TutorDashboardSrsCountersTests::test_tutor_dashboard_shows_srs_due_and_reviewed_today -q
```

Expected:
- Всё ещё FAIL, потому что шаблон пока не выводит “Повтор сегодня”/“Повторил”.

## Task 5: Вывести метрики в шаблоне tutor_dashboard.html (2 места)

**Files:**
- Modify: [tutor_dashboard.html](file:///workspace/core/templates/core/tutor_dashboard.html#L72-L118)
- Modify: [tutor_dashboard.html](file:///workspace/core/templates/core/tutor_dashboard.html#L154-L187)

- [ ] **Step 1: Student card (left list)**

В правом блоке карточки (рядом с “Сегодня: +XP”) добавить две строки:

```html
<div class="mt-0.5 text-[10px] font-bold text-gray-500">Повтор сегодня: {{ student.srs_due_today|default:0 }}</div>
<div class="mt-0.5 text-[10px] font-bold text-gray-500">Повторил: {{ student.srs_reviewed_today|default:0 }}</div>
```

- [ ] **Step 2: Selected student header (right profile)**

В блоке бейджей справа добавить два бейджа:

```html
<span class="hidden md:inline-flex items-center bg-emerald-50 text-emerald-700 border border-emerald-100 px-3 py-2 rounded-lg text-sm font-bold">
    Повтор сегодня: {{ selected_student.srs_due_today|default:0 }}
</span>
<span class="hidden md:inline-flex items-center bg-emerald-50 text-emerald-700 border border-emerald-100 px-3 py-2 rounded-lg text-sm font-bold">
    Повторил: {{ selected_student.srs_reviewed_today|default:0 }}
</span>
```

- [ ] **Step 3: Run tutor dashboard test**

```bash
pytest /workspace/core/tests/test_tutor_dashboard_srs_counters.py::TutorDashboardSrsCountersTests::test_tutor_dashboard_shows_srs_due_and_reviewed_today -q
```

Expected:
- PASS

## Task 6: Полный прогон тестов

- [ ] **Step 1: Run entire test suite**

```bash
pytest -q
```

Expected:
- PASS

## Примечание про коммиты

Я не буду делать git commit автоматически, если вы явно не попросите. Если хотите, могу после реализации собрать изменения в один/несколько коммитов.
