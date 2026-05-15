# Task AI difficulty + tags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Разметить всю базу задач ИИ: абсолютная сложность (1–100) + теги методов/свойств/тем; вычислить относительную сложность (процентили) по экзамену и по типу; показать это и дать фильтры в `tutor_task_bank`.

**Architecture:** 1) Добавляем новые поля в `Task` (AI‑сложность raw + процентили + метаданные) и нормализованные теги `TaskTag` + `Task.tags` M2M. 2) Пишем management command, который батчами прогоняет задачи через OpenRouter, сохраняет raw+теги и пересчитывает процентили. 3) Расширяем `tutor_task_bank`: отображение AI‑метрик и фильтры (по диапазонам и тегам).

**Tech Stack:** Django, OpenRouter (chat completions JSON), Django templates, vanilla JS.

---

## Map of changes (files)

**Create:**
- `core/management/commands/ai_annotate_tasks.py`
- `core/services_task_ai_annotation.py` (вынести промпт/вызов/нормализацию)
- `core/tests/test_task_ai_models.py`
- `core/tests/test_task_ai_annotate_command_smoke.py`
- `core/tests/test_tutor_task_bank_ai_filters.py`

**Modify:**
- `core/models.py` (поля Task + модели TaskTag, M2M)
- `core/migrations/` (новая миграция)
- `core/views.py` (`tutor_task_bank`: annotations + фильтры)
- `core/templates/core/tutor_task_bank.html` (UI бейджей + фильтры)

---

## Task 1: Модели и миграция (AI difficulty + tags)

**Files:**
- Modify: `core/models.py`
- Create: `core/tests/test_task_ai_models.py`

- [ ] **Step 1: Write failing model test (fields + tag relation)**

Create `core/tests/test_task_ai_models.py`:

```python
from django.test import TestCase

from core.models import Subject, ExamFormat, TaskType, Topic, Task


class TaskAIMetadataModelTests(TestCase):
    def test_task_has_ai_fields_defaults(self):
        subject = Subject.objects.create(name="Математика")
        exam_format = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")

        task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="1")
        # Поля должны существовать и быть nullable
        self.assertTrue(hasattr(task, "ai_difficulty_raw"))
        self.assertIsNone(task.ai_difficulty_raw)
        self.assertIsNone(task.ai_difficulty_exam_percentile)
        self.assertIsNone(task.ai_difficulty_type_percentile)
```

- [ ] **Step 2: Run test to verify RED**

Run:
```bash
python manage.py test core.tests.test_task_ai_models
```
Expected: FAIL (атрибутов нет).

- [ ] **Step 3: Implement models in `core/models.py`**

Add to `Task`:

```python
ai_difficulty_raw = models.IntegerField(null=True, blank=True, verbose_name="ИИ: сложность (1-100)")
ai_difficulty_exam_percentile = models.IntegerField(null=True, blank=True, verbose_name="ИИ: сложность (процентиль по экзамену)")
ai_difficulty_type_percentile = models.IntegerField(null=True, blank=True, verbose_name="ИИ: сложность (процентиль по типу)")
ai_annotated_at = models.DateTimeField(null=True, blank=True, verbose_name="ИИ: размечено")
ai_annotation_version = models.CharField(max_length=50, null=True, blank=True, verbose_name="ИИ: версия разметки")
```

Add `TaskTag` model near `Task`:

```python
class TaskTag(models.Model):
    KIND_CHOICES = [
        ("method", "Метод"),
        ("property", "Свойство"),
        ("topic", "Тема"),
        ("other", "Другое"),
    ]
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="other")

    class Meta:
        unique_together = ("kind", "name")
        indexes = [models.Index(fields=["kind", "name"])]

    def __str__(self):
        return f"{self.kind}:{self.name}"
```

And add on `Task`:

```python
ai_tags = models.ManyToManyField("TaskTag", blank=True, related_name="tasks", verbose_name="ИИ: теги")
```

**Normalization rule:** store `TaskTag.name` in normalized form (lower/trim). We will enforce in service layer (not in model).

- [ ] **Step 4: Make migrations + migrate**

Run:
```bash
python manage.py makemigrations core
python manage.py migrate
```

- [ ] **Step 5: Run test to verify GREEN**

Run:
```bash
python manage.py test core.tests.test_task_ai_models
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/models.py core/migrations core/tests/test_task_ai_models.py
git commit -m "feat(task): add AI difficulty fields and tag model"
```

---

## Task 2: Сервис аннотации одной задачи (промпт → OpenRouter → нормализация)

**Files:**
- Create: `core/services_task_ai_annotation.py`

- [ ] **Step 1: Create service skeleton (pure functions + minimal IO)**

Create `core/services_task_ai_annotation.py`:

```python
import json
from dataclasses import dataclass
from typing import List, Optional

from django.utils import timezone

from core.openrouter_client import parse_openrouter_json  # already used elsewhere


ANNOTATION_VERSION = "v1"


def _norm_tag(s: str) -> str:
    s = (s or "").strip().lower()
    s = " ".join(s.split())
    return s


@dataclass
class TaskAIAnnotation:
    difficulty_raw: int
    methods: List[str]
    properties: List[str]
    topics: List[str]
    short_subtype: str = ""


def build_task_annotation_prompt(*, task, exam_format_label: str, task_type_label: str, max_points: int) -> str:
    return (
        f"Ты эксперт по школьной математике и экзаменам. Разметь задачу.\n"
        f"Экзамен: {exam_format_label}\n"
        f"Тип задания: {task_type_label}\n"
        f"Макс. первичный балл: {max_points}\n\n"
        "Верни ТОЛЬКО JSON (без markdown) с полями:\n"
        "- difficulty_raw: integer 1..100 (сложность по содержанию)\n"
        "- methods: array[string] (методы решения)\n"
        "- properties: array[string] (свойства/теоремы/формулы)\n"
        "- topics: array[string] (темы)\n"
        "- short_subtype: string (краткий подтип, 1-4 слова; опционально)\n\n"
        "Условие (HTML):\n"
        f"{task.get_content_for_theme('classic')}\n\n"
        "Решение (HTML, если есть):\n"
        f"{task.get_solution_for_theme('classic')}\n"
    )


def parse_task_annotation(payload: str) -> TaskAIAnnotation:
    data = parse_openrouter_json(payload) if isinstance(payload, str) else (payload or {})
    difficulty_raw = int(data.get("difficulty_raw") or 0)
    if difficulty_raw < 1:
        difficulty_raw = 1
    if difficulty_raw > 100:
        difficulty_raw = 100

    def as_list(x):
        if x is None:
            return []
        if isinstance(x, str):
            return [x]
        if isinstance(x, list):
            return x
        return []

    methods = [_norm_tag(s) for s in as_list(data.get("methods")) if _norm_tag(s)]
    properties = [_norm_tag(s) for s in as_list(data.get("properties")) if _norm_tag(s)]
    topics = [_norm_tag(s) for s in as_list(data.get("topics")) if _norm_tag(s)]
    short_subtype = (data.get("short_subtype") or "").strip()
    return TaskAIAnnotation(difficulty_raw=difficulty_raw, methods=methods, properties=properties, topics=topics, short_subtype=short_subtype)
```

- [ ] **Step 2: Commit**

```bash
git add core/services_task_ai_annotation.py
git commit -m "feat(ai): task annotation service (prompt + parse)"
```

---

## Task 3: Management command: аннотировать задачи батчами + пересчёт процентилей

**Files:**
- Create: `core/management/commands/ai_annotate_tasks.py`
- Create: `core/tests/test_task_ai_annotate_command_smoke.py`

- [ ] **Step 1: Write failing smoke test (command exists)**

Create `core/tests/test_task_ai_annotate_command_smoke.py`:

```python
from django.core.management import call_command
from django.test import TestCase


class TaskAIAnnotateCommandSmokeTests(TestCase):
    def test_command_exists(self):
        # Should not raise
        call_command("ai_annotate_tasks", "--help")
```

- [ ] **Step 2: Run test to verify RED**

Run:
```bash
python manage.py test core.tests.test_task_ai_annotate_command_smoke
```
Expected: FAIL (unknown command).

- [ ] **Step 3: Implement command skeleton**

Create `core/management/commands/ai_annotate_tasks.py` with:
- args:
  - `--subject_id`, `--exam_format_id`, `--task_type_id` (optional filters)
  - `--limit`, `--batch_size`
  - `--force` (re-annotate)
  - `--annotation_version` (default v1)
  - `--dry_run`
  - `--recompute_percentiles_only`
- behavior:
  - select tasks in scope, skip annotated unless `--force` or version differs
  - for each task: call OpenRouter (similar headers/format as existing verify)
  - store `ai_difficulty_raw`, `ai_annotated_at`, `ai_annotation_version`
  - create/get `TaskTag` rows for methods/properties/topics and set M2M
  - after loop: recompute percentiles

**Percentile recompute algorithm (pure DB, deterministic):**
For each `exam_format_id`:
1) get tasks with `task_type__exam_format_id=...` and `ai_difficulty_raw is not null`
2) sort by `(ai_difficulty_raw, id)`
3) percentile = round(100 * rank / (n-1)) where rank from 0..n-1 (if n==1 => 50)

Then within each `task_type_id` similarly.

- [ ] **Step 4: Run smoke test to verify GREEN**

Run:
```bash
python manage.py test core.tests.test_task_ai_annotate_command_smoke
```

- [ ] **Step 5: Commit**

```bash
git add core/management/commands/ai_annotate_tasks.py core/tests/test_task_ai_annotate_command_smoke.py
git commit -m "feat(cmd): batch AI annotation for tasks"
```

---

## Task 4: UI: tutor_task_bank — отображение и фильтры

**Files:**
- Modify: `core/views.py` (tutor_task_bank)
- Modify: `core/templates/core/tutor_task_bank.html`
- Create: `core/tests/test_tutor_task_bank_ai_filters.py`

- [ ] **Step 1: Write failing view/template test for showing AI fields**

Create `core/tests/test_tutor_task_bank_ai_filters.py`:

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Subject, ExamFormat, TaskType, Topic, Task, TaskTag, User


class TutorTaskBankAIFiltersTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="a", password="pw", role="admin")
        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        self.task_type = TaskType.objects.create(exam_format=self.exam_format, number=1, name="Тип 1", max_points=1)
        self.topic = Topic.objects.create(subject=self.subject, name="Тема")

        self.t1 = Task.objects.create(topic=self.topic, task_type=self.task_type, correct_answer="1", ai_difficulty_raw=10, ai_difficulty_exam_percentile=5, ai_difficulty_type_percentile=7)
        self.t2 = Task.objects.create(topic=self.topic, task_type=self.task_type, correct_answer="1", ai_difficulty_raw=80, ai_difficulty_exam_percentile=90, ai_difficulty_type_percentile=95)

        tag = TaskTag.objects.create(kind="method", name="логарифмы")
        self.t2.ai_tags.add(tag)

    def test_renders_ai_fields(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("tutor_task_bank"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "AI сложность")
        self.assertContains(res, "10/100")
        self.assertContains(res, "80/100")
        self.assertContains(res, "логарифмы")
```

- [ ] **Step 2: Run test to verify RED**

Run:
```bash
python manage.py test core.tests.test_tutor_task_bank_ai_filters
```
Expected: FAIL (UI not showing).

- [ ] **Step 3: Add filters in `tutor_task_bank` view**

Add GET params:
- `ai_raw_min`, `ai_raw_max`
- `ai_exam_min`, `ai_exam_max`
- `tag` (id) and/or `tag_q` (contains)

Apply queryset filters:
```python
if ai_raw_min: tasks = tasks.filter(ai_difficulty_raw__gte=int(ai_raw_min))
...
if tag_id: tasks = tasks.filter(ai_tags__id=int(tag_id))
if tag_q: tasks = tasks.filter(ai_tags__name__icontains=tag_q.strip().lower())
```

Pass tag list for filters (top N by frequency in current scope):
```python
available_tags = TaskTag.objects.filter(tasks__in=tasks_scope).annotate(c=models.Count("tasks")).order_by("-c", "name")[:200]
```

- [ ] **Step 4: Update template**

In `core/templates/core/tutor_task_bank.html`:
- add filter inputs (min/max + tag select + text)
- add per-task row:
  - `AI сложность: {{ task.ai_difficulty_raw|default:"—" }}/100`
  - `Экзамен: {{ task.ai_difficulty_exam_percentile|default:"—" }}%`
  - `Тип: {{ task.ai_difficulty_type_percentile|default:"—" }}%`
  - badges for `task.ai_tags.all` (first 6)

- [ ] **Step 5: Run test to verify GREEN**

Run:
```bash
python manage.py test core.tests.test_tutor_task_bank_ai_filters
```

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/templates/core/tutor_task_bank.html core/tests/test_tutor_task_bank_ai_filters.py
git commit -m "feat(ui): show AI difficulty and tags in tutor task bank"
```

---

## Task 5: Regression + docs for running annotation

**Files:**
- Modify: `README.md` or `docs/` (optional)

- [ ] **Step 1: Run full test suite**

Run:
```bash
python manage.py test core.tests
```

- [ ] **Step 2: Add short runbook (how to run annotation)**

Create `docs/ai-task-annotation-runbook.md`:
- example commands:
  - annotate only one exam format
  - recompute percentiles only
  - force re-run

- [ ] **Step 3: Commit + push**

```bash
git add docs/ai-task-annotation-runbook.md
git commit -m "docs: add task AI annotation runbook"
git push origin main
```

---

## Self-review checklist
- Spec coverage: поля Task + теги + прогон по базе + процентили + tutor_task_bank UI/filters — покрыто Tasks 1–4.
- Placeholder scan: no TODO/TBD in code steps.
- Naming consistency: `ai_difficulty_raw`, `ai_tags`, command `ai_annotate_tasks`.

