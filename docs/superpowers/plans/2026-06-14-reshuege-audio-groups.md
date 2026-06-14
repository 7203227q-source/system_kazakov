# Reshuege Audio Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add audio import, audio deduplication, shared task context groups, and atomic grouped selection for `РешуОГЭ/РешуЕГЭ` tasks.

**Architecture:** Extend the existing `РешуОГЭ/РешуЕГЭ` import path with a narrow audio layer instead of a global media refactor. Store audio in `TaskAudioAsset`, group related tasks in `TaskContextGroup`, connect tasks through `Task.context_group`, and update the assignment generator to treat grouped tasks as atomic bundles.

**Tech Stack:** Django 6, Django ORM migrations, existing `services_reshuege.py` import pipeline, local media storage, Django TestCase, existing tutor assignment builder flow.

---

## File Structure

**Create**
- `core/migrations/0069_task_audio_groups.py` — schema for audio assets, context groups, and task relation.
- `core/tests/test_reshuege_audio_import.py` — import and dedup tests for audio assets and context groups.
- `core/tests/test_assignment_context_group_generator.py` — generator tests for atomic inclusion of grouped tasks.
- `core/services_reshuege_audio.py` — focused helpers for audio URL normalization, hashing, download, dedup, and group assignment.

**Modify**
- `core/models.py` — add `TaskAudioAsset`, `TaskContextGroup`, and `Task.context_group`.
- `core/admin.py` — register audio assets and context groups for inspection.
- `core/services_reshuege.py` — detect audio on import, call audio service, assign groups to tasks.
- `core/views.py` — update assignment builder to include full `TaskContextGroup` atomically.
- `core/tests/test_sdamgia_bundle_import.py` — extend existing import coverage with group assertions where useful.
- `docs/superpowers/specs/2026-06-14-reshuege-audio-groups-design.md` — only if implementation reveals terminology drift.

---

### Task 1: Add Audio Asset And Context Group Models

**Files:**
- Create: `core/migrations/0069_task_audio_groups.py`
- Create: `core/tests/test_reshuege_audio_import.py`
- Modify: `core/models.py`
- Modify: `core/admin.py`

- [ ] **Step 1: Write the failing model tests**

```python
from django.db import IntegrityError
from django.test import TestCase

from core.models import ExamFormat, Subject, Task, TaskAudioAsset, TaskContextGroup, Topic


class ReshuegeAudioModelTests(TestCase):
    def test_context_group_can_share_one_audio_asset_across_many_tasks(self):
        subject = Subject.objects.create(name="Английский язык")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ английский", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subject, name="Аудирование")
        asset = TaskAudioAsset.objects.create(
            source="reshuege",
            original_url="https://ege.sdamgia.ru/audio/example.mp3",
            file="tasks/audio/example.mp3",
            sha256="abc123",
            mime_type="audio/mpeg",
            size_bytes=12345,
        )
        group = TaskContextGroup.objects.create(
            source="reshuege",
            group_key="audio:https://ege.sdamgia.ru/audio/example.mp3",
            audio_asset=asset,
            subject=subject,
            exam_format=exam_format,
        )
        task1 = Task.objects.create(topic=topic, correct_answer="1", difficulty=10, exam_points=1, context_group=group)
        task2 = Task.objects.create(topic=topic, correct_answer="2", difficulty=15, exam_points=1, context_group=group)

        self.assertEqual(task1.context_group.audio_asset_id, asset.id)
        self.assertEqual(task2.context_group.audio_asset_id, asset.id)

    def test_audio_asset_sha256_is_unique_per_source(self):
        TaskAudioAsset.objects.create(
            source="reshuege",
            original_url="https://ege.sdamgia.ru/audio/a.mp3",
            file="tasks/audio/a.mp3",
            sha256="samehash",
            mime_type="audio/mpeg",
            size_bytes=10,
        )
        with self.assertRaises(IntegrityError):
            TaskAudioAsset.objects.create(
                source="reshuege",
                original_url="https://ege.sdamgia.ru/audio/b.mp3",
                file="tasks/audio/b.mp3",
                sha256="samehash",
                mime_type="audio/mpeg",
                size_bytes=10,
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_reshuege_audio_import.ReshuegeAudioModelTests -v 2`
Expected: FAIL with `ImportError` / `AttributeError` because `TaskAudioAsset`, `TaskContextGroup`, and `Task.context_group` do not exist.

- [ ] **Step 3: Write minimal implementation**

Add new models to `core/models.py`:

```python
class TaskAudioAsset(models.Model):
    SOURCE_CHOICES = [
        ("reshuege", "РешуОГЭ/ЕГЭ"),
    ]

    source = models.CharField(max_length=32, choices=SOURCE_CHOICES)
    original_url = models.URLField(max_length=1000)
    file = models.FileField(upload_to="tasks/audio/")
    sha256 = models.CharField(max_length=64)
    mime_type = models.CharField(max_length=128, blank=True, default="")
    size_bytes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("source", "original_url"), name="uniq_task_audio_asset_source_url"),
            models.UniqueConstraint(fields=("source", "sha256"), name="uniq_task_audio_asset_source_sha256"),
        ]


class TaskContextGroup(models.Model):
    SOURCE_CHOICES = [
        ("reshuege", "РешуОГЭ/ЕГЭ"),
    ]

    source = models.CharField(max_length=32, choices=SOURCE_CHOICES)
    group_key = models.CharField(max_length=1000)
    audio_asset = models.ForeignKey(TaskAudioAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name="context_groups")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="task_context_groups")
    exam_format = models.ForeignKey(ExamFormat, on_delete=models.SET_NULL, null=True, blank=True, related_name="task_context_groups")
    title = models.CharField(max_length=255, blank=True, default="")
    position_hint = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("source", "group_key"), name="uniq_task_context_group_source_key"),
        ]


class Task(models.Model):
    context_group = models.ForeignKey(
        "TaskContextGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
```

Register models in `core/admin.py`:

```python
@admin.register(TaskAudioAsset)
class TaskAudioAssetAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "original_url", "sha256", "size_bytes", "created_at")
    search_fields = ("original_url", "sha256")
    list_filter = ("source",)


@admin.register(TaskContextGroup)
class TaskContextGroupAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "group_key", "audio_asset", "subject", "exam_format", "created_at")
    search_fields = ("group_key", "title", "position_hint")
    list_filter = ("source", "subject", "exam_format")
```

Create migration `core/migrations/0069_task_audio_groups.py` with `CreateModel` operations for `TaskAudioAsset`, `TaskContextGroup`, and `AddField` for `Task.context_group`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_reshuege_audio_import.ReshuegeAudioModelTests -v 2`
Expected: PASS with 2 tests.

- [ ] **Step 5: Commit**

```bash
git add core/models.py core/admin.py core/migrations/0069_task_audio_groups.py core/tests/test_reshuege_audio_import.py
git commit -m "feat: add reshuege audio asset models"
```

### Task 2: Add Audio Download And Dedup Service

**Files:**
- Create: `core/services_reshuege_audio.py`
- Create: `core/tests/test_reshuege_audio_import.py`
- Modify: `core/models.py`

- [ ] **Step 1: Write the failing service tests**

```python
from io import BytesIO
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from core.models import TaskAudioAsset
from core.services_reshuege_audio import get_or_create_audio_asset


@override_settings(MEDIA_ROOT="/tmp/kazakov-test-media")
class ReshuegeAudioDedupTests(TestCase):
    @patch("core.services_reshuege_audio.requests.get")
    def test_reuses_existing_asset_by_original_url_without_redownload(self, mocked_get):
        existing = TaskAudioAsset.objects.create(
            source="reshuege",
            original_url="https://oge.sdamgia.ru/files/example.mp3",
            file="tasks/audio/existing.mp3",
            sha256="hash1",
            mime_type="audio/mpeg",
            size_bytes=100,
        )

        asset = get_or_create_audio_asset(
            source="reshuege",
            original_url="https://oge.sdamgia.ru/files/example.mp3",
        )

        self.assertEqual(asset.id, existing.id)
        mocked_get.assert_not_called()

    @patch("core.services_reshuege_audio.requests.get")
    def test_reuses_existing_asset_by_sha256_after_download(self, mocked_get):
        TaskAudioAsset.objects.create(
            source="reshuege",
            original_url="https://oge.sdamgia.ru/files/old.mp3",
            file="tasks/audio/old.mp3",
            sha256="samehash",
            mime_type="audio/mpeg",
            size_bytes=3,
        )

        mocked_get.return_value.status_code = 200
        mocked_get.return_value.headers = {"Content-Type": "audio/mpeg"}
        mocked_get.return_value.content = b"abc"

        with patch("core.services_reshuege_audio.compute_sha256_hex", return_value="samehash"):
            asset = get_or_create_audio_asset(
                source="reshuege",
                original_url="https://oge.sdamgia.ru/files/new.mp3",
            )

        self.assertEqual(asset.original_url, "https://oge.sdamgia.ru/files/old.mp3")
        self.assertEqual(TaskAudioAsset.objects.count(), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_reshuege_audio_import.ReshuegeAudioDedupTests -v 2`
Expected: FAIL because `core.services_reshuege_audio` and `get_or_create_audio_asset()` do not exist.

- [ ] **Step 3: Write minimal implementation**

Create `core/services_reshuege_audio.py`:

```python
import hashlib
import os
from urllib.parse import urlparse

import requests
from django.core.files.base import ContentFile

from core.models import TaskAudioAsset


def compute_sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_audio_url(url: str) -> str:
    return (url or "").strip()


def build_audio_filename(original_url: str) -> str:
    parsed = urlparse(original_url)
    base = os.path.basename(parsed.path) or "audio.bin"
    return base


def get_or_create_audio_asset(*, source: str, original_url: str) -> TaskAudioAsset:
    normalized_url = normalize_audio_url(original_url)
    existing = TaskAudioAsset.objects.filter(source=source, original_url=normalized_url).first()
    if existing:
        return existing

    response = requests.get(normalized_url, timeout=30)
    response.raise_for_status()
    content = response.content
    sha256 = compute_sha256_hex(content)

    existing_by_hash = TaskAudioAsset.objects.filter(source=source, sha256=sha256).first()
    if existing_by_hash:
        return existing_by_hash

    asset = TaskAudioAsset(
        source=source,
        original_url=normalized_url,
        sha256=sha256,
        mime_type=(response.headers.get("Content-Type") or "").strip(),
        size_bytes=len(content),
    )
    asset.file.save(build_audio_filename(normalized_url), ContentFile(content), save=False)
    asset.save()
    return asset
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_reshuege_audio_import.ReshuegeAudioDedupTests -v 2`
Expected: PASS with 2 tests.

- [ ] **Step 5: Commit**

```bash
git add core/services_reshuege_audio.py core/tests/test_reshuege_audio_import.py
git commit -m "feat: add reshuege audio dedup service"
```

### Task 3: Add Audio And Group Assignment In Import

**Files:**
- Modify: `core/services_reshuege.py`
- Modify: `core/tests/test_sdamgia_bundle_import.py`
- Create: `core/tests/test_reshuege_audio_import.py`
- Modify: `core/services_reshuege_audio.py`

- [ ] **Step 1: Write the failing import tests**

```python
from unittest.mock import patch

from django.test import TestCase

from core.models import ExamFormat, Subject, Task, TaskAudioAsset, TaskContextGroup, TaskType, Topic
from core.services_reshuege import import_one_task_from_sdamgia


class ReshuegeAudioImportTests(TestCase):
    def setUp(self):
        subject = Subject.objects.create(name="Английский язык")
        self.exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ английский", year=2026, is_active=True)
        Topic.objects.create(subject=subject, name="Задания из Открытого Банка")
        for n in range(1, 6):
            TaskType.objects.create(exam_format=self.exam_format, number=n, name=f"Тип {n}", max_points=1)

    def test_import_creates_shared_audio_group_for_bundle(self):
        html = '''
        <html><body>
          <audio controls src="/files/audio123.mp3"></audio>
          <div id="body1001">Тип 1 № 1001</div>
          <div id="sol1001">Ответ: 1</div>
          <div class="expand" data-open="Показать другие задания этого блока">
            <div class="prob_maindiv">Тип 2 № 1002</div>
            <div class="prob_maindiv">Тип 3 № 1003</div>
            <div class="prob_maindiv">Тип 4 № 1004</div>
            <div class="prob_maindiv">Тип 5 № 1005</div>
          </div>
        </body></html>
        '''

        with patch("core.services_reshuege.fetch_task_page_html", side_effect=lambda *_args, **_kwargs: html), \
             patch("core.services_reshuege.download_and_replace_images", side_effect=lambda h, *_args, **_kwargs: h), \
             patch("core.services_reshuege_audio.get_or_create_audio_asset") as mocked_audio:
            asset = TaskAudioAsset.objects.create(
                source="reshuege",
                original_url="https://en-oge.sdamgia.ru/files/audio123.mp3",
                file="tasks/audio/audio123.mp3",
                sha256="hash123",
                mime_type="audio/mpeg",
                size_bytes=10,
            )
            mocked_audio.return_value = asset

            import_one_task_from_sdamgia(
                exam_format_id=self.exam_format.id,
                type_number=1,
                task_id="1001",
                base_url="https://en-oge.sdamgia.ru",
                skip_no_answer=False,
                skip_prototype=False,
                skip_no_solution=False,
                skip_existing=True,
                exclude_larin=False,
                theme="classic",
            )

        tasks = list(Task.objects.filter(fipi_id__in=["1001", "1002", "1003", "1004", "1005"]).order_by("fipi_id"))
        self.assertEqual(len(tasks), 5)
        group_ids = {task.context_group_id for task in tasks}
        self.assertEqual(len(group_ids), 1)
        group = tasks[0].context_group
        self.assertEqual(group.audio_asset_id, asset.id)
        self.assertEqual(group.source, "reshuege")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_reshuege_audio_import.ReshuegeAudioImportTests -v 2`
Expected: FAIL because import does not parse audio or assign `context_group`.

- [ ] **Step 3: Write minimal implementation**

Add helpers to `core/services_reshuege_audio.py`:

```python
from bs4 import BeautifulSoup

from core.models import TaskContextGroup


def extract_audio_url(html: str, *, base_url: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    audio = soup.select_one("audio[src], source[src]")
    if not audio:
        return ""
    return urljoin(base_url, audio.get("src") or "")


def build_group_key(*, audio_url: str) -> str:
    return f"audio:{normalize_audio_url(audio_url)}"


def get_or_create_context_group(*, subject, exam_format, audio_asset, group_key):
    group, _ = TaskContextGroup.objects.get_or_create(
        source="reshuege",
        group_key=group_key,
        defaults={
            "audio_asset": audio_asset,
            "subject": subject,
            "exam_format": exam_format,
        },
    )
    if group.audio_asset_id is None and audio_asset is not None:
        group.audio_asset = audio_asset
        group.save(update_fields=["audio_asset"])
    return group
```

Update `import_one_task_from_sdamgia()` in `core/services_reshuege.py`:

```python
audio_url = extract_audio_url(html, base_url=base_url)
context_group = None
if audio_url:
    audio_asset = get_or_create_audio_asset(source="reshuege", original_url=audio_url)
    group_key = build_group_key(audio_url=audio_url)
    context_group = get_or_create_context_group(
        subject=exam_format.subject,
        exam_format=exam_format,
        audio_asset=audio_asset,
        group_key=group_key,
    )
...
task_obj.context_group = context_group
task_obj.save(update_fields=["context_group", ...])
```

When recursively importing bundle siblings, reuse the same `context_group` if already resolved for the root task.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_reshuege_audio_import.ReshuegeAudioImportTests core.tests.test_sdamgia_bundle_import -v 2`
Expected: PASS with shared context-group behavior preserved alongside existing bundle import behavior.

- [ ] **Step 5: Commit**

```bash
git add core/services_reshuege.py core/services_reshuege_audio.py core/tests/test_reshuege_audio_import.py core/tests/test_sdamgia_bundle_import.py
git commit -m "feat: import reshuege audio groups"
```

### Task 4: Make Assignment Generator Treat Groups Atomically

**Files:**
- Create: `core/tests/test_assignment_context_group_generator.py`
- Modify: `core/views.py`
- Modify: `core/models.py`
- Modify: existing assignment builder template only if output text needs to explain grouped additions

- [ ] **Step 1: Write the failing generator tests**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, Task, TaskAudioAsset, TaskContextGroup, TaskType, Topic, User


class AssignmentContextGroupGeneratorTests(TestCase):
    def test_generator_adds_entire_context_group(self):
        tutor = User.objects.create_user(username="tutor", password="pass", role="tutor")
        student = User.objects.create_user(username="student", password="pass", role="student")
        tutor.students.add(student)

        subject = Subject.objects.create(name="Английский язык")
        exam_format = ExamFormat.objects.create(subject=subject, name="ОГЭ английский", year=2026, is_active=True)
        topic = Topic.objects.create(subject=subject, name="Аудирование")
        task_type = TaskType.objects.create(exam_format=exam_format, number=1, name="Аудирование", max_points=1)
        asset = TaskAudioAsset.objects.create(
            source="reshuege",
            original_url="https://en-oge.sdamgia.ru/files/audio123.mp3",
            file="tasks/audio/audio123.mp3",
            sha256="hash123",
            mime_type="audio/mpeg",
            size_bytes=10,
        )
        group = TaskContextGroup.objects.create(
            source="reshuege",
            group_key="audio:https://en-oge.sdamgia.ru/files/audio123.mp3",
            audio_asset=asset,
            subject=subject,
            exam_format=exam_format,
        )
        for idx in range(1, 6):
            Task.objects.create(
                topic=topic,
                task_type=task_type,
                fipi_id=f"200{idx}",
                correct_answer=str(idx),
                difficulty=10,
                exam_points=1,
                context_group=group,
            )

        self.client.login(username="tutor", password="pass")
        response = self.client.post(
            reverse("tutor_create_assignment"),
            {
                "student_id": student.id,
                "exam_format": exam_format.id,
                "part": "test",
                "task_type_ranges": f"{task_type.id}:1",
            },
        )

        self.assertEqual(response.status_code, 302)
        assignment = tutor.assignments.order_by("-id").first()
        self.assertEqual(assignment.tasks.count(), 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_assignment_context_group_generator -v 2`
Expected: FAIL because the generator currently treats grouped tasks as independent tasks.

- [ ] **Step 3: Write minimal implementation**

In `core/views.py`, extract helper near assignment generation:

```python
def expand_tasks_with_context_groups(tasks):
    ordered = []
    seen_task_ids = set()
    seen_group_ids = set()
    for task in tasks:
        group_id = getattr(task, "context_group_id", None)
        if group_id:
            if group_id in seen_group_ids:
                continue
            group_tasks = list(
                Task.objects.filter(context_group_id=group_id).select_related("task_type", "topic").order_by("task_type__number", "id")
            )
            if not group_tasks:
                continue
            for grouped_task in group_tasks:
                if grouped_task.id not in seen_task_ids:
                    ordered.append(grouped_task)
                    seen_task_ids.add(grouped_task.id)
            seen_group_ids.add(group_id)
        else:
            if task.id not in seen_task_ids:
                ordered.append(task)
                seen_task_ids.add(task.id)
    return ordered
```

Apply it at the point where selected tasks are finalized before `assignment.tasks.set(...)`:

```python
selected_tasks = expand_tasks_with_context_groups(selected_tasks)
assignment.tasks.set(selected_tasks)
```

If the builder enforces strict task-count limits, check grouped size before adding:

```python
candidate_group_tasks = list(Task.objects.filter(context_group_id=group_id))
if len(current_tasks) + len(candidate_group_tasks) > requested_limit:
    continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_assignment_context_group_generator core.tests.test_exam_structure_boundaries_in_generator -v 2`
Expected: PASS for grouped inclusion and for the nearby existing builder boundary behavior.

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/tests/test_assignment_context_group_generator.py
git commit -m "feat: keep reshuege audio groups together in generator"
```

### Task 5: Run Focused Regression Suite

**Files:**
- Test: `core/tests/test_reshuege_audio_import.py`
- Test: `core/tests/test_sdamgia_bundle_import.py`
- Test: `core/tests/test_assignment_context_group_generator.py`
- Test: `core/tests/test_exam_structure_boundaries_in_generator.py`
- Test: `core/tests/test_tutor_create_assignment_dynamic_exam_format.py`

- [ ] **Step 1: Run import and audio tests**

Run: `python manage.py test core.tests.test_reshuege_audio_import core.tests.test_sdamgia_bundle_import -v 2`
Expected: PASS.

- [ ] **Step 2: Run generator tests**

Run: `python manage.py test core.tests.test_assignment_context_group_generator core.tests.test_exam_structure_boundaries_in_generator core.tests.test_tutor_create_assignment_dynamic_exam_format -v 2`
Expected: PASS.

- [ ] **Step 3: Run migrations check**

Run: `python manage.py makemigrations --check`
Expected: If the repository is otherwise clean, `No changes detected`. If legacy rename-only migration noise still exists, record it explicitly and do not conflate it with this feature.

- [ ] **Step 4: Run lint on touched files**

Run: `ruff check core/models.py core/admin.py core/services_reshuege.py core/services_reshuege_audio.py core/views.py core/tests/test_reshuege_audio_import.py core/tests/test_sdamgia_bundle_import.py core/tests/test_assignment_context_group_generator.py`
Expected: `All checks passed!` for new files; if `core/views.py` still has legacy lint debt, record it separately from new changes.

- [ ] **Step 5: Commit**

```bash
git add core/models.py core/admin.py core/services_reshuege.py core/services_reshuege_audio.py core/views.py core/tests/test_reshuege_audio_import.py core/tests/test_sdamgia_bundle_import.py core/tests/test_assignment_context_group_generator.py docs/superpowers/plans/2026-06-14-reshuege-audio-groups.md
git commit -m "test: verify reshuege audio group rollout"
```

## Self-Review Notes

- Spec coverage:
  - dedicated audio asset model: Tasks 1 and 2
  - context groups and task relation: Tasks 1 and 3
  - audio import and dedup by URL/hash: Tasks 2 and 3
  - atomic grouped selection in generator: Task 4
  - non-regression for import/generator: Task 5
- No placeholders remain.
- Naming consistency is locked to:
  - `TaskAudioAsset`
  - `TaskContextGroup`
  - `Task.context_group`
  - `get_or_create_audio_asset()`
  - `get_or_create_context_group()`
  - `expand_tasks_with_context_groups()`
