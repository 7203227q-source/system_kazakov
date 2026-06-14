# School Track Math Grade 7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a separate `school` track for `Математика, 7 класс` with curriculum models, non-exam assignment flow, student learning plans, and draft-only AI task generation.

**Architecture:** Keep the current `exam` flow intact and add a parallel `school` flow. Reuse `Task`, `Assignment`, `Submission`, and `StudentSubjectProfile`, but store school-only structure in new curriculum and plan models plus a task metadata layer. Keep AI generation in draft mode behind explicit school metadata so it cannot pollute exam tasks.

**Tech Stack:** Django 6, Django ORM migrations, Django admin, server-rendered views/templates, pytest/Django TestCase, existing OpenRouter integration.

---

## File Structure

**Create**
- `core/migrations/0064_school_track_models.py` — schema for school track, curriculum, plan, and school task metadata.
- `core/migrations/0065_seed_math_grade7_track.py` — seed `Математика, 7 класс` and starter curriculum skeleton.
- `core/tests/test_school_track_models.py` — model constraints and seed coverage.
- `core/tests/test_school_assignment_flow.py` — school assignment builder behavior.
- `core/tests/test_school_learning_plan.py` — diagnostics-to-plan behavior.
- `core/tests/test_school_ai_generation.py` — draft AI generation behavior.
- `core/services_school_plan.py` — plan creation and updates from diagnostics / solved tasks.
- `core/services_school_ai.py` — prompt building, parsing, and draft task creation for school mode.

**Modify**
- `core/models.py` — add school track, curriculum, plan, and task metadata models.
- `core/admin.py` — register and expose new school models in admin.
- `core/views.py` — add school builder flow and learning-plan endpoints or helper views.
- `core/urls.py` — routes for school assignment creation and learning plan screens/actions.
- `core/openrouter_client.py` — reuse low-level API helper if school generator needs a shared request function.
- `core/templates/` existing tutor/student templates related to assignment builder and plan display.
- `docs/superpowers/specs/2026-06-14-school-track-math-grade-7-design.md` — only if design terminology must be synchronized after implementation discoveries.

---

### Task 1: Add School Data Model

**Files:**
- Create: `core/migrations/0064_school_track_models.py`
- Create: `core/migrations/0065_seed_math_grade7_track.py`
- Create: `core/tests/test_school_track_models.py`
- Modify: `core/models.py`
- Modify: `core/admin.py`

- [ ] **Step 1: Write the failing model tests**

```python
from django.test import TestCase

from core.models import (
    CurriculumTopic,
    CurriculumUnit,
    LearningTaskType,
    LearningTrack,
    SchoolTaskMeta,
    Subject,
    Task,
    Topic,
    User,
)


class SchoolTrackModelTests(TestCase):
    def test_seeded_math_grade7_track_exists(self):
        track = LearningTrack.objects.get(mode="school", grade=7, title="Математика, 7 класс")
        self.assertEqual(track.subject.name, "Математика")
        self.assertTrue(track.is_active)

    def test_curriculum_topic_order_is_scoped_to_unit(self):
        subject = Subject.objects.create(name="Алгебра")
        track = LearningTrack.objects.create(subject=subject, mode="school", grade=7, title="Алгебра, 7 класс")
        unit = CurriculumUnit.objects.create(track=track, title="Рациональные числа", position=1)
        CurriculumTopic.objects.create(unit=unit, title="Обыкновенные дроби", position=1, is_required=True)
        with self.assertRaises(Exception):
            CurriculumTopic.objects.create(unit=unit, title="Десятичные дроби", position=1, is_required=True)

    def test_school_task_meta_allows_task_without_exam_format(self):
        subject = Subject.objects.create(name="Математика")
        track = LearningTrack.objects.create(subject=subject, mode="school", grade=7, title="Математика, 7 класс")
        unit = CurriculumUnit.objects.create(track=track, title="Уравнения", position=1)
        topic = CurriculumTopic.objects.create(unit=unit, title="Линейные уравнения", position=1, is_required=True)
        learning_type = LearningTaskType.objects.create(
            track=track,
            code="linear-basic",
            name="Уравнение в одно действие",
            default_max_points=1,
            is_extended_answer=False,
        )
        legacy_topic = Topic.objects.create(subject=subject, name="Линейные уравнения")
        task = Task.objects.create(topic=legacy_topic, correct_answer="5", difficulty=20, exam_points=1)

        meta = SchoolTaskMeta.objects.create(
            task=task,
            learning_track=track,
            curriculum_topic=topic,
            learning_task_type=learning_type,
            difficulty_level=2,
            status="published",
        )

        self.assertEqual(meta.learning_track.title, "Математика, 7 класс")
        self.assertIsNone(task.task_type)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_school_track_models -v 2`
Expected: FAIL with `ImportError` / `AttributeError` because `LearningTrack`, `CurriculumUnit`, `SchoolTaskMeta` and related models do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add new models in `core/models.py`:

```python
class LearningTrack(models.Model):
    MODE_CHOICES = [
        ("school", "Школьная программа"),
    ]

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="learning_tracks")
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    grade = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=200)
    academic_year = models.CharField(max_length=32, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("subject", "mode", "grade", "title"),
                name="uniq_learning_track_subject_mode_grade_title",
            )
        ]


class CurriculumUnit(models.Model):
    learning_track = models.ForeignKey(LearningTrack, on_delete=models.CASCADE, related_name="units")
    title = models.CharField(max_length=200)
    position = models.PositiveIntegerField()
    description = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=("learning_track", "position"),
                name="uniq_curriculum_unit_track_position",
            )
        ]


class CurriculumTopic(models.Model):
    unit = models.ForeignKey(CurriculumUnit, on_delete=models.CASCADE, related_name="topics")
    legacy_topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name="curriculum_topics")
    title = models.CharField(max_length=200)
    position = models.PositiveIntegerField()
    difficulty_baseline = models.PositiveSmallIntegerField(default=1)
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=("unit", "position"), name="uniq_curriculum_topic_unit_position")
        ]


class LearningTaskType(models.Model):
    learning_track = models.ForeignKey(LearningTrack, on_delete=models.CASCADE, related_name="learning_task_types")
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    default_max_points = models.PositiveSmallIntegerField(default=1)
    is_extended_answer = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("learning_track", "code"),
                name="uniq_learning_task_type_track_code",
            )
        ]


class SchoolTaskMeta(models.Model):
    STATUS_CHOICES = [
        ("draft", "Черновик"),
        ("published", "Опубликовано"),
    ]

    task = models.OneToOneField(Task, on_delete=models.CASCADE, related_name="school_meta")
    learning_track = models.ForeignKey(LearningTrack, on_delete=models.CASCADE, related_name="task_meta")
    curriculum_topic = models.ForeignKey(CurriculumTopic, on_delete=models.CASCADE, related_name="task_meta")
    learning_task_type = models.ForeignKey(LearningTaskType, on_delete=models.CASCADE, related_name="task_meta")
    difficulty_level = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
```

Seed `Математика, 7 класс` and starter units in `core/migrations/0065_seed_math_grade7_track.py`:

```python
def forwards(apps, schema_editor):
    Subject = apps.get_model("core", "Subject")
    LearningTrack = apps.get_model("core", "LearningTrack")
    CurriculumUnit = apps.get_model("core", "CurriculumUnit")

    math, _ = Subject.objects.get_or_create(name="Математика")
    track, _ = LearningTrack.objects.get_or_create(
        subject=math,
        mode="school",
        grade=7,
        title="Математика, 7 класс",
        defaults={"is_active": True},
    )
    for position, title in enumerate(
        [
            "Рациональные числа",
            "Алгебраические выражения",
            "Линейные уравнения",
            "Геометрические фигуры",
        ],
        start=1,
    ):
        CurriculumUnit.objects.get_or_create(
            learning_track=track,
            position=position,
            defaults={"title": title},
        )
```

Register new admin models in `core/admin.py`:

```python
@admin.register(LearningTrack)
class LearningTrackAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "mode", "grade", "is_active")
    list_filter = ("mode", "grade", "is_active", "subject")


@admin.register(SchoolTaskMeta)
class SchoolTaskMetaAdmin(admin.ModelAdmin):
    list_display = ("task", "learning_track", "curriculum_topic", "learning_task_type", "difficulty_level", "status")
    list_filter = ("learning_track", "curriculum_topic", "learning_task_type", "status")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_school_track_models -v 2`
Expected: PASS with 3 tests.

- [ ] **Step 5: Commit**

```bash
git add core/models.py core/admin.py core/migrations/0064_school_track_models.py core/migrations/0065_seed_math_grade7_track.py core/tests/test_school_track_models.py
git commit -m "feat: add school track core models"
```

### Task 2: Add Student Learning Plan Service

**Files:**
- Create: `core/services_school_plan.py`
- Create: `core/tests/test_school_learning_plan.py`
- Modify: `core/models.py`
- Modify: `core/admin.py`

- [ ] **Step 1: Write the failing plan tests**

```python
from django.test import TestCase

from core.models import CurriculumTopic, CurriculumUnit, LearningTrack, StudentLearningPlan, Subject, User
from core.services_school_plan import create_initial_learning_plan, update_learning_plan_after_result


class SchoolLearningPlanTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="student", password="pass", role="student")
        subject = Subject.objects.create(name="Математика")
        self.track = LearningTrack.objects.create(subject=subject, mode="school", grade=7, title="Математика, 7 класс")
        unit = CurriculumUnit.objects.create(learning_track=self.track, title="Уравнения", position=1)
        self.topic1 = CurriculumTopic.objects.create(unit=unit, title="Уравнение в одно действие", position=1, is_required=True)
        self.topic2 = CurriculumTopic.objects.create(unit=unit, title="Уравнение в два действия", position=2, is_required=True)

    def test_create_initial_learning_plan_orders_topics_by_diagnostic_score(self):
        plan = create_initial_learning_plan(
            student=self.student,
            track=self.track,
            diagnostic_scores={
                self.topic1.id: 0.2,
                self.topic2.id: 0.8,
            },
            goal_type="подтянуть базу",
        )
        items = list(plan.items.order_by("-priority", "id"))
        self.assertEqual(items[0].curriculum_topic_id, self.topic1.id)
        self.assertEqual(items[0].status, "assigned")

    def test_update_learning_plan_after_result_schedules_repeat_for_low_accuracy(self):
        plan = create_initial_learning_plan(
            student=self.student,
            track=self.track,
            diagnostic_scores={self.topic1.id: 0.4, self.topic2.id: 0.6},
            goal_type="идти по школьной программе",
        )
        item = plan.items.get(curriculum_topic=self.topic1)

        update_learning_plan_after_result(item=item, accuracy=0.3)
        item.refresh_from_db()

        self.assertEqual(item.status, "repeat")
        self.assertIsNotNone(item.next_review_at)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_school_learning_plan -v 2`
Expected: FAIL because `StudentLearningPlan`, `PlanItem`, and `core.services_school_plan` are not fully implemented.

- [ ] **Step 3: Write minimal implementation**

Extend `core/models.py`:

```python
class StudentLearningPlan(models.Model):
    GOAL_CHOICES = [
        ("подтянуть базу", "Подтянуть базу"),
        ("идти по школьной программе", "Идти по школьной программе"),
        ("ускоренный проход", "Ускоренный проход"),
    ]
    STATUS_CHOICES = [
        ("draft", "Черновик"),
        ("active", "Активный"),
        ("completed", "Завершён"),
    ]

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="learning_plans")
    learning_track = models.ForeignKey(LearningTrack, on_delete=models.CASCADE, related_name="learning_plans")
    goal_type = models.CharField(max_length=64, choices=GOAL_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    diagnostic_completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_learning_plans")
    updated_at = models.DateTimeField(auto_now=True)


class PlanItem(models.Model):
    STATUS_CHOICES = [
        ("assigned", "Назначено"),
        ("in_progress", "В работе"),
        ("repeat", "Повторить"),
        ("mastered", "Освоено"),
    ]

    plan = models.ForeignKey(StudentLearningPlan, on_delete=models.CASCADE, related_name="items")
    curriculum_topic = models.ForeignKey(CurriculumTopic, on_delete=models.CASCADE, related_name="plan_items")
    priority = models.PositiveSmallIntegerField(default=1)
    target_mastery = models.DecimalField(max_digits=4, decimal_places=2, default=0.80)
    recommended_task_count = models.PositiveSmallIntegerField(default=5)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="assigned")
    next_review_at = models.DateTimeField(null=True, blank=True)
```

Create `core/services_school_plan.py`:

```python
from datetime import timedelta

from django.utils import timezone

from core.models import PlanItem, StudentLearningPlan


def create_initial_learning_plan(*, student, track, diagnostic_scores, goal_type, created_by=None):
    plan = StudentLearningPlan.objects.create(
        student=student,
        learning_track=track,
        goal_type=goal_type,
        status="active",
        diagnostic_completed_at=timezone.now(),
        created_by=created_by,
    )
    ordered_pairs = sorted(diagnostic_scores.items(), key=lambda pair: pair[1])
    max_priority = len(ordered_pairs)
    for index, (topic_id, score) in enumerate(ordered_pairs):
        PlanItem.objects.create(
            plan=plan,
            curriculum_topic_id=topic_id,
            priority=max_priority - index,
            target_mastery=0.80,
            recommended_task_count=7 if score < 0.5 else 5,
            status="assigned",
        )
    return plan


def update_learning_plan_after_result(*, item, accuracy):
    if accuracy < 0.6:
        item.status = "repeat"
        item.next_review_at = timezone.now() + timedelta(days=3)
    elif accuracy >= 0.85:
        item.status = "mastered"
        item.next_review_at = None
    else:
        item.status = "in_progress"
    item.save(update_fields=["status", "next_review_at"])
    return item
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_school_learning_plan -v 2`
Expected: PASS with 2 tests.

- [ ] **Step 5: Commit**

```bash
git add core/models.py core/admin.py core/services_school_plan.py core/tests/test_school_learning_plan.py
git commit -m "feat: add school learning plan service"
```

### Task 3: Add School Assignment Builder Flow

**Files:**
- Create: `core/tests/test_school_assignment_flow.py`
- Modify: `core/views.py`
- Modify: `core/urls.py`
- Modify: `core/models.py`
- Modify: `core/templates/` assignment builder template used by `tutor_create_assignment`

- [ ] **Step 1: Write the failing builder tests**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import (
    CurriculumTopic,
    CurriculumUnit,
    LearningTaskType,
    LearningTrack,
    SchoolTaskMeta,
    Subject,
    Task,
    Topic,
    User,
)


class SchoolAssignmentFlowTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="tutor", password="pass", role="tutor")
        self.student = User.objects.create_user(username="student", password="pass", role="student")
        self.tutor.students.add(self.student)
        self.subject = Subject.objects.create(name="Математика")
        self.track = LearningTrack.objects.create(subject=self.subject, mode="school", grade=7, title="Математика, 7 класс")
        self.unit = CurriculumUnit.objects.create(learning_track=self.track, title="Уравнения", position=1)
        self.curriculum_topic = CurriculumTopic.objects.create(unit=self.unit, title="Линейные уравнения", position=1, is_required=True)
        self.learning_type = LearningTaskType.objects.create(
            learning_track=self.track,
            code="linear-basic",
            name="Уравнение в одно действие",
            default_max_points=1,
            is_extended_answer=False,
        )
        legacy_topic = Topic.objects.create(subject=self.subject, name="Линейные уравнения")
        self.task = Task.objects.create(topic=legacy_topic, correct_answer="7", difficulty=20, exam_points=1)
        SchoolTaskMeta.objects.create(
            task=self.task,
            learning_track=self.track,
            curriculum_topic=self.curriculum_topic,
            learning_task_type=self.learning_type,
            difficulty_level=2,
            status="published",
        )

    def test_tutor_create_assignment_shows_school_track_filters(self):
        self.client.login(username="tutor", password="pass")
        response = self.client.get(reverse("tutor_create_assignment"), {"student_id": self.student.id, "mode": "school"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Математика, 7 класс")
        self.assertContains(response, "Линейные уравнения")
        self.assertNotContains(response, "ЕГЭ")

    def test_tutor_can_create_school_assignment_without_exam_format(self):
        self.client.login(username="tutor", password="pass")
        response = self.client.post(
            reverse("tutor_create_assignment"),
            {
                "student_id": self.student.id,
                "mode": "school",
                "learning_track": self.track.id,
                "curriculum_topic": self.curriculum_topic.id,
                "learning_task_type": self.learning_type.id,
                "tasks_per_type": 1,
                "title": "7 класс: линейные уравнения",
            },
        )
        self.assertEqual(response.status_code, 302)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_school_assignment_flow -v 2`
Expected: FAIL because the builder currently requires exam-centric filters and does not understand `mode=school`.

- [ ] **Step 3: Write minimal implementation**

Add optional school fields on `Assignment` in `core/models.py`:

```python
class Assignment(models.Model):
    assignment_mode = models.CharField(
        max_length=20,
        choices=[("exam", "Экзамен"), ("school", "Школьная программа")],
        default="exam",
    )
    learning_track = models.ForeignKey("LearningTrack", on_delete=models.SET_NULL, null=True, blank=True, related_name="assignments")
    curriculum_topic = models.ForeignKey("CurriculumTopic", on_delete=models.SET_NULL, null=True, blank=True, related_name="assignments")
    learning_task_type = models.ForeignKey("LearningTaskType", on_delete=models.SET_NULL, null=True, blank=True, related_name="assignments")
```

Add school branch in `core/views.py` inside `tutor_create_assignment`:

```python
mode = (request.GET.get("mode") or request.POST.get("mode") or "exam").strip()
if mode == "school":
    track_id = request.GET.get("learning_track") or request.POST.get("learning_track")
    topic_id = request.GET.get("curriculum_topic") or request.POST.get("curriculum_topic")
    learning_type_id = request.GET.get("learning_task_type") or request.POST.get("learning_task_type")
    school_tracks = LearningTrack.objects.filter(mode="school", is_active=True).select_related("subject")
    selected_track = school_tracks.filter(pk=track_id).first() if track_id else school_tracks.first()
    available_topics = CurriculumTopic.objects.filter(unit__learning_track=selected_track).select_related("unit") if selected_track else CurriculumTopic.objects.none()
    available_learning_types = LearningTaskType.objects.filter(learning_track=selected_track) if selected_track else LearningTaskType.objects.none()

    if request.method == "POST":
        task_qs = (
            Task.objects.filter(
                school_meta__learning_track_id=track_id,
                school_meta__curriculum_topic_id=topic_id,
                school_meta__learning_task_type_id=learning_type_id,
                school_meta__status="published",
            )
            .distinct()
            .order_by("difficulty", "id")
        )
        selected_tasks = list(task_qs[: int(request.POST.get("tasks_per_type", "1"))])
        assignment = Assignment.objects.create(
            student=student,
            tutor=request.user,
            title=request.POST.get("title") or f"{selected_track.title}: {available_topics.get(pk=topic_id).title}",
            assignment_mode="school",
            learning_track_id=track_id,
            curriculum_topic_id=topic_id,
            learning_task_type_id=learning_type_id,
            is_published=False,
        )
        assignment.tasks.set(selected_tasks)
        return redirect("tutor_preview_assignment", assignment_id=assignment.id)
```

Add URL-compatible query handling in `core/urls.py` by keeping the same route and branch in the existing view.

Template branch to display school filters:

```django
{% if mode == "school" %}
  <select name="learning_track">{% for track in school_tracks %}<option value="{{ track.id }}">{{ track.title }}</option>{% endfor %}</select>
  <select name="curriculum_topic">{% for topic in available_topics %}<option value="{{ topic.id }}">{{ topic.title }}</option>{% endfor %}</select>
  <select name="learning_task_type">{% for item in available_learning_types %}<option value="{{ item.id }}">{{ item.name }}</option>{% endfor %}</select>
{% endif %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_school_assignment_flow -v 2`
Expected: PASS with 2 tests.

- [ ] **Step 5: Commit**

```bash
git add core/models.py core/views.py core/urls.py core/tests/test_school_assignment_flow.py core/templates
git commit -m "feat: add school assignment builder flow"
```

### Task 4: Add Diagnostics-To-Plan Entry Point

**Files:**
- Modify: `core/views.py`
- Modify: `core/urls.py`
- Create: `core/tests/test_school_learning_plan.py`
- Modify: `core/services_school_plan.py`

- [ ] **Step 1: Write the failing view test**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import CurriculumTopic, CurriculumUnit, LearningTrack, Subject, User


class SchoolDiagnosticStartTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="tutor", password="pass", role="tutor")
        self.student = User.objects.create_user(username="student", password="pass", role="student")
        self.tutor.students.add(self.student)
        subject = Subject.objects.create(name="Математика")
        self.track = LearningTrack.objects.create(subject=subject, mode="school", grade=7, title="Математика, 7 класс")
        unit = CurriculumUnit.objects.create(learning_track=self.track, title="Уравнения", position=1)
        self.topic = CurriculumTopic.objects.create(unit=unit, title="Линейные уравнения", position=1, is_required=True)

    def test_tutor_can_start_plan_from_diagnostic_scores(self):
        self.client.login(username="tutor", password="pass")
        response = self.client.post(
            reverse("tutor_start_school_plan"),
            {
                "student_id": self.student.id,
                "learning_track": self.track.id,
                f"topic_{self.topic.id}": "0.25",
                "goal_type": "подтянуть базу",
            },
        )
        self.assertEqual(response.status_code, 302)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_school_learning_plan.SchoolDiagnosticStartTests -v 2`
Expected: FAIL with `NoReverseMatch` because the route and controller do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add route in `core/urls.py`:

```python
path("tutor/student/<int:student_id>/school-plan/start/", views.tutor_start_school_plan, name="tutor_start_school_plan"),
```

Add view in `core/views.py`:

```python
@login_required
def tutor_start_school_plan(request, student_id):
    if request.user.role != "tutor":
        return HttpResponseForbidden("Only tutors can start school plans.")
    student = get_object_or_404(User, pk=student_id)
    if student not in request.user.students.all():
        return HttpResponseForbidden("Student is not linked to this tutor.")
    if request.method != "POST":
        return HttpResponseBadRequest("POST required.")

    track = get_object_or_404(LearningTrack, pk=request.POST.get("learning_track"), mode="school")
    diagnostic_scores = {}
    for topic in CurriculumTopic.objects.filter(unit__learning_track=track):
        raw = request.POST.get(f"topic_{topic.id}")
        if raw not in (None, ""):
            diagnostic_scores[topic.id] = float(raw)
    plan = create_initial_learning_plan(
        student=student,
        track=track,
        diagnostic_scores=diagnostic_scores,
        goal_type=request.POST.get("goal_type") or "идти по школьной программе",
        created_by=request.user,
    )
    return redirect("tutor_student_history", student_id=student.id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_school_learning_plan.SchoolDiagnosticStartTests -v 2`
Expected: PASS with 1 test.

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/urls.py core/services_school_plan.py core/tests/test_school_learning_plan.py
git commit -m "feat: add school diagnostic plan entrypoint"
```

### Task 5: Add Draft-Only AI Generation For School Tasks

**Files:**
- Create: `core/services_school_ai.py`
- Create: `core/tests/test_school_ai_generation.py`
- Modify: `core/models.py`
- Modify: `core/admin.py`
- Modify: `core/views.py`

- [ ] **Step 1: Write the failing AI generation tests**

```python
from unittest.mock import patch

from django.test import TestCase

from core.models import CurriculumTopic, CurriculumUnit, LearningTaskType, LearningTrack, Subject, User
from core.services_school_ai import generate_school_task_draft


class SchoolAIGenerationTests(TestCase):
    @patch("core.services_school_ai.call_openrouter_json")
    def test_generate_school_task_draft_creates_draft_meta(self, mocked_call):
        mocked_call.return_value = {
            "content_html": "<p>Решите уравнение: x + 5 = 9</p>",
            "correct_answer": "4",
            "solution_html": "<p>x = 4</p>",
            "hints": ["Перенесите 5 в другую часть"],
        }
        subject = Subject.objects.create(name="Математика")
        track = LearningTrack.objects.create(subject=subject, mode="school", grade=7, title="Математика, 7 класс")
        unit = CurriculumUnit.objects.create(learning_track=track, title="Уравнения", position=1)
        topic = CurriculumTopic.objects.create(unit=unit, title="Линейные уравнения", position=1, is_required=True)
        learning_type = LearningTaskType.objects.create(
            learning_track=track,
            code="linear-basic",
            name="Уравнение в одно действие",
            default_max_points=1,
            is_extended_answer=False,
        )
        tutor = User.objects.create_user(username="tutor", password="pass", role="tutor")

        task = generate_school_task_draft(
            actor=tutor,
            curriculum_topic=topic,
            learning_task_type=learning_type,
            difficulty_level=2,
        )

        self.assertEqual(task.school_meta.status, "draft")
        self.assertEqual(task.correct_answer, "4")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_school_ai_generation -v 2`
Expected: FAIL because `core.services_school_ai` and the generation entry point do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add draft provenance fields to `SchoolTaskMeta` in `core/models.py`:

```python
generated_by_ai = models.BooleanField(default=False)
generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="generated_school_tasks")
generation_notes = models.JSONField(default=dict, blank=True)
```

Create `core/services_school_ai.py`:

```python
from core.models import SchoolTaskMeta, Task, TaskVariant
from core.services_openrouter import call_openrouter_json


def generate_school_task_draft(*, actor, curriculum_topic, learning_task_type, difficulty_level):
    prompt = {
        "topic": curriculum_topic.title,
        "task_type": learning_task_type.name,
        "difficulty_level": difficulty_level,
        "output_schema": ["content_html", "correct_answer", "solution_html", "hints"],
    }
    payload = call_openrouter_json(prompt)
    task = Task.objects.create(
        topic=curriculum_topic.legacy_topic,
        correct_answer=payload["correct_answer"],
        difficulty=difficulty_level * 25,
        exam_points=learning_task_type.default_max_points,
    )
    TaskVariant.objects.create(
        task=task,
        theme="classic",
        content=payload["content_html"],
        solution=payload["solution_html"],
    )
    SchoolTaskMeta.objects.create(
        task=task,
        learning_track=curriculum_topic.unit.learning_track,
        curriculum_topic=curriculum_topic,
        learning_task_type=learning_task_type,
        difficulty_level=difficulty_level,
        status="draft",
        generated_by_ai=True,
        generated_by=actor,
        generation_notes={"hints": payload.get("hints", [])},
    )
    return task
```

Expose admin moderation in `core/admin.py`:

```python
@admin.action(description="Опубликовать черновики school-задач")
def publish_school_drafts(modeladmin, request, queryset):
    queryset.update(status="published")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_school_ai_generation -v 2`
Expected: PASS with 1 test.

- [ ] **Step 5: Commit**

```bash
git add core/models.py core/admin.py core/services_school_ai.py core/tests/test_school_ai_generation.py
git commit -m "feat: add draft school ai generation"
```

### Task 6: Run Focused Regression Suite

**Files:**
- Test: `core/tests/test_school_track_models.py`
- Test: `core/tests/test_school_learning_plan.py`
- Test: `core/tests/test_school_assignment_flow.py`
- Test: `core/tests/test_school_ai_generation.py`
- Test: `core/tests/test_tutor_create_assignment_dynamic_exam_format.py`

- [ ] **Step 1: Run the new school test suite**

Run: `python manage.py test core.tests.test_school_track_models core.tests.test_school_learning_plan core.tests.test_school_assignment_flow core.tests.test_school_ai_generation -v 2`
Expected: PASS for all new school tests.

- [ ] **Step 2: Run the nearby exam regression test**

Run: `python manage.py test core.tests.test_tutor_create_assignment_dynamic_exam_format -v 2`
Expected: PASS to confirm the `exam` builder still works.

- [ ] **Step 3: Run migrations check**

Run: `python manage.py makemigrations --check`
Expected: `No changes detected`.

- [ ] **Step 4: Run lint on touched files**

Run: `ruff check core/models.py core/admin.py core/views.py core/urls.py core/services_school_plan.py core/services_school_ai.py core/tests/test_school_track_models.py core/tests/test_school_learning_plan.py core/tests/test_school_assignment_flow.py core/tests/test_school_ai_generation.py`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add core/models.py core/admin.py core/views.py core/urls.py core/services_school_plan.py core/services_school_ai.py core/tests/test_school_track_models.py core/tests/test_school_learning_plan.py core/tests/test_school_assignment_flow.py core/tests/test_school_ai_generation.py docs/superpowers/plans/2026-06-14-school-track-math-grade-7.md
git commit -m "test: verify school track mvp rollout"
```

## Self-Review Notes

- Spec coverage:
  - separate `school` contour: Tasks 1 and 3
  - curriculum and school task types: Task 1
  - student learning plan: Tasks 2 and 4
  - AI generation in draft mode: Task 5
  - non-regression for `exam` flow: Task 6
- No placeholders remain.
- Naming consistency is locked to:
  - `LearningTrack`
  - `CurriculumUnit`
  - `CurriculumTopic`
  - `LearningTaskType`
  - `SchoolTaskMeta`
  - `StudentLearningPlan`
  - `PlanItem`
