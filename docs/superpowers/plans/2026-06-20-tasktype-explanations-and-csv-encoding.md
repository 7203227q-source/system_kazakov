# TaskType Explanations + CSV Encoding Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить пояснения к типам заданий (включая отдельный текст для английского) и показывать их на экранах ученика/репетитора/в банке/в журналах; починить «кракозябры» при CSV-импорте из-за кодировки.

**Architecture:** Хранить пояснения на уровне `TaskType` (RU + EN). Для предмета «Английский язык» автоматически использовать EN (если заполнено), иначе RU. Отрисовывать `task.task_type.explanation_effective` во всех нужных шаблонах.

**Tech Stack:** Django (models/migrations/views/templates), Django TestCase.

---

## File Structure

**Modify:**
- `core/models.py` — поля `TaskType.explanation`, `TaskType.explanation_en`, вычисляемое свойство `explanation_effective`.
- `core/admin.py` — (опционально) добавить поле в `list_display`/`search_fields` для удобства.
- `core/views.py` — расширить `select_related` там, где рендерится `TaskType.explanation_effective`; добавить `task__task_type` в `student_history`.
- `core/services_csv.py` — безопасное декодирование CSV (utf-8-sig/utf-8/cp1251 fallback).
- `core/templates/core/*.html` — вывод пояснений на экранах ученика/репетитора/банка/журнала + редактор в `admin_exam_structure.html`.
- `core/templates/core/import_tasks.html` — подсказка про кодировку CSV.

**Create:**
- `core/migrations/00xx_tasktype_explanations.py` — миграция на новые поля `TaskType`.
- `core/tests/test_tasktype_explanations.py` — тесты выбора effective-пояснения.
- `core/tests/test_csv_import_encoding.py` — тесты импорта CSV в cp1251/utf-8-sig.
- (при необходимости) `core/tests/test_tasktype_explanations_rendering.py` — smoke-тесты рендера на ключевых страницах.

---

### Task 1: Add TaskType Explanation Fields + Effective Selector

**Files:**
- Modify: `core/models.py`
- Modify: `core/admin.py`
- Create: `core/tests/test_tasktype_explanations.py`
- Create: `core/migrations/00xx_tasktype_explanations.py`

- [ ] **Step 1: Write failing tests for effective explanation**

```python
from django.test import TestCase

from core.models import ExamFormat, Subject, TaskType


class TaskTypeExplanationEffectiveTests(TestCase):
    def test_english_subject_prefers_explanation_en(self):
        subj = Subject.objects.create(name="Английский язык")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ английский", year=2026, is_active=True)
        tt = TaskType.objects.create(
            exam_format=ef,
            number=1,
            name="Тип 1",
            max_points=1,
            explanation="RU",
            explanation_en="EN",
        )
        self.assertEqual(tt.explanation_effective, "EN")

    def test_non_english_subject_uses_explanation(self):
        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ЕГЭ математика", year=2026, is_active=True)
        tt = TaskType.objects.create(
            exam_format=ef,
            number=1,
            name="Тип 1",
            max_points=1,
            explanation="RU",
            explanation_en="EN",
        )
        self.assertEqual(tt.explanation_effective, "RU")

    def test_english_subject_falls_back_to_ru_when_en_empty(self):
        subj = Subject.objects.create(name="Английский язык")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ английский", year=2026, is_active=True)
        tt = TaskType.objects.create(
            exam_format=ef,
            number=1,
            name="Тип 1",
            max_points=1,
            explanation="RU",
            explanation_en="",
        )
        self.assertEqual(tt.explanation_effective, "RU")
```

- [ ] **Step 2: Run tests to confirm they fail**

Run:
```bash
python manage.py test core.tests.test_tasktype_explanations -v 2
```

Expected: FAIL (нет полей/свойства).

- [ ] **Step 3: Add model fields + property**

```python
class TaskType(models.Model):
    exam_format = models.ForeignKey(ExamFormat, on_delete=models.CASCADE, related_name='task_types')
    number = models.IntegerField(verbose_name="Номер в КИМе")
    name = models.CharField(max_length=200, verbose_name="Краткое описание типа")
    max_points = models.IntegerField(default=1, verbose_name="Максимальный балл")
    is_geometry = models.BooleanField(default=False, verbose_name="Геометрия (для ОГЭ)")
    is_extended_answer = models.BooleanField(default=False, verbose_name="Развёрнутый ответ (часть 2)")
    explanation = models.TextField(blank=True, default="", verbose_name="Пояснение (RU)")
    explanation_en = models.TextField(blank=True, default="", verbose_name="Пояснение (EN)")

    @property
    def explanation_effective(self):
        subj_name = (getattr(getattr(self.exam_format, "subject", None), "name", "") or "").strip().lower()
        if "англ" in subj_name:
            v = (self.explanation_en or "").strip()
            if v:
                return v
        return (self.explanation or "").strip()
```

- [ ] **Step 4: Create and apply migration**

Run:
```bash
python manage.py makemigrations core
python manage.py migrate
```

Expected: миграция добавляет 2 поля в таблицу `core_tasktype`.

- [ ] **Step 5: Re-run tests**

Run:
```bash
python manage.py test core.tests.test_tasktype_explanations -v 2
```

Expected: PASS.

---

### Task 2: Make Explanations Editable in Admin Exam Structure Page

**Files:**
- Modify: `core/views.py` (view `admin_exam_structure`)
- Modify: `core/templates/core/admin_exam_structure.html`
- Modify: `core/tests/test_admin_exam_structure_editor.py`

- [ ] **Step 1: Extend existing test to post explanations**

```python
def test_admin_can_update_tasktype_names(self):
    self.client.login(username="a", password="pass")
    res = self.client.post(
        reverse("admin_exam_structure"),
        {
            "exam_format_id": str(self.ef.id),
            f"name_{self.tt1.id}": "Планиметрия",
            f"name_{self.tt2.id}": "Алгебра",
            f"explanation_{self.tt1.id}": "Пояснение RU",
            f"explanation_en_{self.tt1.id}": "Explanation EN",
        },
    )
    self.assertEqual(res.status_code, 302)
    self.tt1.refresh_from_db()
    self.assertEqual(self.tt1.name, "Планиметрия")
    self.assertEqual(self.tt1.explanation, "Пояснение RU")
    self.assertEqual(self.tt1.explanation_en, "Explanation EN")
```

- [ ] **Step 2: Run this test to confirm it fails**

Run:
```bash
python manage.py test core.tests.test_admin_exam_structure_editor -v 2
```

Expected: FAIL (view/template не сохраняют поля).

- [ ] **Step 3: Update view saving logic**

В `admin_exam_structure` при POST:
- читать `explanation_{id}` и `explanation_en_{id}` по каждому `TaskType`
- сохранять изменения через `update_fields=["name","explanation","explanation_en"]` (по факту изменённых полей)

Код-скелет:
```python
for tt in task_types:
    name_raw = request.POST.get(f"name_{tt.id}")
    exp_raw = request.POST.get(f"explanation_{tt.id}")
    exp_en_raw = request.POST.get(f"explanation_en_{tt.id}")

    changed_fields = []
    if name_raw is not None:
        name = name_raw.strip()
        if name and name != tt.name:
            tt.name = name
            changed_fields.append("name")

    if exp_raw is not None:
        exp = exp_raw.strip()
        if exp != (tt.explanation or ""):
            tt.explanation = exp
            changed_fields.append("explanation")

    if exp_en_raw is not None:
        exp_en = exp_en_raw.strip()
        if exp_en != (tt.explanation_en or ""):
            tt.explanation_en = exp_en
            changed_fields.append("explanation_en")

    if changed_fields:
        tt.save(update_fields=changed_fields)
        changed += 1
```

- [ ] **Step 4: Update template to render editable textareas**

В `admin_exam_structure.html` добавить колонки:
- `Пояснение (RU)`
- `Пояснение (EN)`

Минимальный вариант: в колонке «Название» (или отдельными колонками) добавить 2 `<textarea>`:
```html
<textarea name="explanation_{{ t.id }}" class="w-full mt-2 border border-gray-300 rounded-lg px-3 py-2 text-xs bg-white" rows="2">{{ t.explanation }}</textarea>
<textarea name="explanation_en_{{ t.id }}" class="w-full mt-2 border border-gray-300 rounded-lg px-3 py-2 text-xs bg-white" rows="2">{{ t.explanation_en }}</textarea>
```

- [ ] **Step 5: Re-run tests**

Run:
```bash
python manage.py test core.tests.test_admin_exam_structure_editor -v 2
```

Expected: PASS.

---

### Task 3: Render Explanations on Student Pages (Variant + Journal + Summary)

**Files:**
- Modify: `core/views.py` (`student_solve_assignment`, `student_history`)
- Modify: `core/templates/core/student_solve_assignment.html`
- Modify: `core/templates/core/student_history.html`
- Modify: `core/templates/core/student_assignment_summary.html`
- (optional) Create: `core/tests/test_tasktype_explanations_rendering.py`

- [ ] **Step 1: Add missing select_related in student_history**

Update queryset:
```python
submissions_qs = (
    Submission.objects.filter(student=request.user)
    .select_related(
        "task",
        "task__topic",
        "task__topic__subject",
        "task__task_type",
        "task__task_type__exam_format",
        "task__task_type__exam_format__subject",
        "assignment",
    )
    .prefetch_related("comments", "comments__author")
    .order_by("-created_at", "-id")
)
```

- [ ] **Step 2: Expand select_related in student_solve_assignment tasks**

Update:
```python
tasks = assignment.tasks.select_related(
    "task_type",
    "task_type__exam_format",
    "task_type__exam_format__subject",
).order_by("task_type__number", "id")
```

- [ ] **Step 3: Render explanation in student_solve_assignment**

In header block around `{{ task.task_type.label }}` render:
```html
{% if task.task_type and task.task_type.explanation_effective %}
    <div class="text-xs text-gray-500 whitespace-pre-line normal-case font-normal mt-1">
        {{ task.task_type.explanation_effective }}
    </div>
{% endif %}
```

- [ ] **Step 4: Render explanation in student_history**

Под заголовком/темой:
```html
{% if sub.task.task_type and sub.task.task_type.explanation_effective %}
    <p class="text-xs text-gray-500 mt-1 whitespace-pre-line">
        {{ sub.task.task_type.explanation_effective }}
    </p>
{% endif %}
```

- [ ] **Step 5: Render explanation in student_assignment_summary**

В «Сводке по задачам» добавить второй строкой рядом с label:
```html
{% if item.task.task_type and item.task.task_type.explanation_effective %}
    <div class="text-xs text-gray-500 whitespace-pre-line">
        {{ item.task.task_type.explanation_effective }}
    </div>
{% endif %}
```

И в «Подробном разборе» в шапке карточки задачи — аналогично.

- [ ] **Step 6: Add smoke tests for rendering**

Минимум: проверить, что пояснение присутствует в HTML на двух маршрутах.

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Assignment, ExamFormat, Subject, Task, TaskType, TaskVariant, Topic, User


class TaskTypeExplanationRenderingTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create(username="t", role="tutor")
        self.student = User.objects.create(username="s", role="student")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1, explanation="Пояснение")
        topic = Topic.objects.create(subject=subject, name="Тема")
        task = Task.objects.create(topic=topic, task_type=tt, correct_answer="0")
        TaskVariant.objects.create(task=task, theme="classic", content="<p>x</p>", solution="<p>y</p>")
        self.assignment = Assignment.objects.create(tutor=self.tutor, student=self.student, title="Вариант", exam_format=exam)
        self.assignment.tasks.add(task)

    def test_student_variant_shows_explanation(self):
        self.client.force_login(self.student)
        res = self.client.get(reverse("student_solve_assignment", args=[self.assignment.id]))
        self.assertEqual(res.status_code, 200)
        self.assertIn("Пояснение", res.content.decode("utf-8"))
```

- [ ] **Step 7: Run tests**

Run:
```bash
python manage.py test core.tests.test_tasktype_explanations_rendering -v 2
```

Expected: PASS.

---

### Task 4: Render Explanations on Tutor Pages (Bank + Journal + Assignment Views)

**Files:**
- Modify: `core/views.py` (querysets: `tutor_task_bank`, `tutor_assignment_view`, `tutor_preview_assignment`)
- Modify: `core/templates/core/tutor_task_bank.html`
- Modify: `core/templates/core/tutor_student_history.html`
- Modify: `core/templates/core/tutor_assignment_view.html`
- Modify: `core/templates/core/tutor_preview_assignment.html`
- Modify: `core/templates/core/tutor_create_assignment.html`

- [ ] **Step 1: Add select_related depth where needed**

Examples:
- `tutor_task_bank` tasks queryset:
```python
Task.objects.select_related("topic", "task_type", "task_type__exam_format", "task_type__exam_format__subject")
```

- `tutor_assignment_view` and `tutor_preview_assignment` tasks querysets: добавить `task_type__exam_format__subject`.

- [ ] **Step 2: Bank of tasks (карточка задачи)**

В `tutor_task_bank.html` рядом с `{{ task.task_type.name }}`:
```html
{% if task.task_type and task.task_type.explanation_effective %}
    <div class="text-xs text-gray-500 mt-1 whitespace-pre-line">
        {{ task.task_type.explanation_effective }}
    </div>
{% endif %}
```

- [ ] **Step 3: Tutor assignment view**

В `tutor_assignment_view.html` под `{{ item.task.task_type.label }}` — аналогично.

- [ ] **Step 4: Tutor student history**

В `tutor_student_history.html` под `{{ sub.task.task_type.label }}` (в обеих ветках шаблона) — аналогично.

- [ ] **Step 5: Tutor preview assignment**

В `tutor_preview_assignment.html` под `№{{ task.task_type.number }}. {{ task.task_type.name }}` — аналогично.

- [ ] **Step 6: Tutor create assignment**

В `tutor_create_assignment.html` в заголовке группы типа рядом с `{{ group.type.label }}` добавить пояснение:
```html
{% if group.type and group.type.explanation_effective %}
    <div class="text-xs text-gray-500 mt-1 whitespace-pre-line">
        {{ group.type.explanation_effective }}
    </div>
{% endif %}
```

- [ ] **Step 7: Add a minimal test (optional)**

Если нужен smoke для `tutor_task_bank`:
```python
res = self.client.get(reverse("tutor_task_bank"))
self.assertIn("Пояснение", res.content.decode("utf-8"))
```

---

### Task 5: Fix CSV Import Encoding (No More Garbled Text)

**Files:**
- Modify: `core/services_csv.py`
- Modify: `core/templates/core/import_tasks.html`
- Create: `core/tests/test_csv_import_encoding.py`

- [ ] **Step 1: Write failing test for cp1251 CSV**

```python
import io

from django.test import TestCase

from core.models import ExamFormat, Subject, Task, TaskType
from core.services_csv import import_tasks_from_csv


class CsvImportEncodingTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        TaskType.objects.create(exam_format=self.exam, number=1, name="Тип 1", max_points=1)

    def test_import_cp1251_decodes_russian(self):
        csv_text = (
            "fipi_id,type_number,subtype_tag,difficulty,correct_answer,theme,content,solution\n"
            "abc,1,,50,1,classic,Привет,Решение\n"
        )
        raw = csv_text.encode("cp1251")
        f = io.BytesIO(raw)
        created, updated = import_tasks_from_csv(f, self.exam.id)
        self.assertEqual(created, 1)
        t = Task.objects.get(fipi_id="abc")
        self.assertIn("Привет", t.variants.get(theme="classic").content)
```

- [ ] **Step 2: Run test to confirm it fails**

Run:
```bash
python manage.py test core.tests.test_csv_import_encoding -v 2
```

Expected: FAIL (кракозябры/UnicodeDecodeError).

- [ ] **Step 3: Implement robust decoding in import_tasks_from_csv**

Replace `decode('utf-8')` with fallback decode:
```python
raw = file_obj.read() or b""
decoded_file = None
for enc in ("utf-8-sig", "utf-8", "cp1251"):
    try:
        decoded_file = raw.decode(enc)
        break
    except UnicodeDecodeError:
        continue
if decoded_file is None:
    decoded_file = raw.decode("utf-8", errors="replace")
```

- [ ] **Step 4: Update import UI help text**

В `import_tasks.html` добавить строку:
- «Кодировка файла: UTF-8 (желательно) / UTF-8 with BOM / CP1251 — поддерживается автоматически».

- [ ] **Step 5: Re-run tests**

Run:
```bash
python manage.py test core.tests.test_csv_import_encoding -v 2
```

Expected: PASS.

---

### Task 6: Full Regression Test Run

**Files:**
- Test-only

- [ ] **Step 1: Run core test suite**

Run:
```bash
python manage.py test core -v 2
```

Expected: PASS.

