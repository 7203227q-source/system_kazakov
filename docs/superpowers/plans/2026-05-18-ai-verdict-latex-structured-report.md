# AI-Вердикт по фото: структурный LaTeX-отчёт Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать структурный отчёт ИИ-проверки по фото (распознано → ошибки → снятие баллов → итог) с LaTeX во всех секциях и серверным антифрод-гейтом (0 баллов за нерелевантное/нечитабельное фото).

**Architecture:** Один вызов модели возвращает расширенный JSON. Бэкенд валидирует/нормализует результат, применяет гейт по `photo_valid`/`recognition_confidence`, сохраняет структурные поля в `Submission`, возвращает данные фронту. UI показывает секции и отдельно “Снятие баллов”.

**Tech Stack:** Django views/templates, Django TestCase.

---

## Files (map)

**Modify**
- [views.py](file:///workspace/core/views.py#L5217-L5602) — `api_verify_with_ai` (+ зеркально `api_tutor_verify_with_ai`) и `api_clear_uploaded_photos`
- [models.py](file:///workspace/core/models.py#L377-L416) — `Submission`: новые поля хранения
- [student_solve_assignment.html](file:///workspace/core/templates/core/student_solve_assignment.html#L179-L267) — серверный рендер секции “Снятие баллов” + JS `verifyWithAI()` для динамического рендера

**Create**
- `/workspace/core/tests/test_ai_verdict_antifraud_and_breakdown.py`
- `/workspace/core/migrations/0055_submission_ai_photo_valid_and_breakdown.py`

---

### Task 1: RED — тесты антифрода и нормализации LaTeX в структурных полях

**Files:**
- Create: `/workspace/core/tests/test_ai_verdict_antifraud_and_breakdown.py`

- [ ] **Step 1: Write failing tests**

```python
import base64
import json
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import (
    ExamFormat,
    OpenRouterModel,
    Subject,
    SubjectAIConfig,
    Submission,
    Task,
    TaskType,
    TaskVariant,
    Topic,
    User,
)


class AIVerdictAntiFraudAndBreakdownTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Математика")
        self.exam_format = ExamFormat.objects.create(subject=self.subject, name="ЕГЭ", year=2026, is_active=True)
        self.task_type = TaskType.objects.create(
            exam_format=self.exam_format,
            number=20,
            name="Тип 20",
            max_points=2,
            is_extended_answer=True,
        )
        self.topic = Topic.objects.create(subject=self.subject, name="T")
        self.task = Task.objects.create(topic=self.topic, task_type=self.task_type, correct_answer="1", difficulty=10, exam_points=2)
        TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="<p>S</p>")

        self.student = User.objects.create_user(username="st1", email="st1@example.com", password="pass", role="student")

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X2nGkAAAAASUVORK5CYII="
        )
        image = SimpleUploadedFile("a.png", png_bytes, content_type="image/png")
        self.submission = Submission.objects.create(student=self.student, task=self.task, image_url=image)

        model_obj = OpenRouterModel.objects.create(code="test-model", label="Test", capabilities="vision")
        SubjectAIConfig.objects.create(subject=self.subject, photo_analysis_model=model_obj)

        os.environ["OPENROUTER_API_KEY"] = "test"

    def test_forces_zero_when_photo_invalid_even_if_model_gives_points(self):
        structured = {
            "primary_score": 2,
            "is_correct": True,
            "photo_valid": False,
            "photo_valid_reason": "На фото не решение этой задачи.",
            "recognition_confidence": 0.9,
            "recognized_solution": "Похоже на кота.",
            "mistakes": [],
            "verdict": ["ОК"],
            "score_breakdown": [{"label": "К1", "awarded": 2, "max": 2, "reason": "ОК"}],
            "feedback": "",
        }
        dummy_response = {"choices": [{"message": {"content": json.dumps(structured, ensure_ascii=False)}}]}

        from unittest.mock import patch

        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response
            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.submission.id]))

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["primary_score"], 0)
        self.assertFalse(data["is_correct"])
        self.submission.refresh_from_db()
        self.assertEqual(int(self.submission.primary_score or 0), 0)
        self.assertFalse(bool(self.submission.is_correct))
        self.assertIn("На фото не решение", self.submission.ai_feedback or "")

    def test_forces_zero_when_confidence_below_threshold(self):
        structured = {
            "primary_score": 1,
            "is_correct": False,
            "photo_valid": True,
            "photo_valid_reason": "",
            "recognition_confidence": 0.1,
            "recognized_solution": "[неразборчиво]",
            "mistakes": [],
            "verdict": ["Неуверенность распознавания: высокая."],
            "score_breakdown": [{"label": "К1", "awarded": 1, "max": 2, "reason": "частично"}],
            "feedback": "",
        }
        dummy_response = {"choices": [{"message": {"content": json.dumps(structured, ensure_ascii=False)}}]}

        from unittest.mock import patch

        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response
            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.submission.id]))

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["primary_score"], 0)
        self.assertFalse(data["is_correct"])

    def test_normalizes_latex_in_recognized_solution_and_breakdown_reason(self):
        structured = {
            "primary_score": 1,
            "is_correct": False,
            "photo_valid": True,
            "photo_valid_reason": "",
            "recognition_confidence": 0.9,
            "recognized_solution": "frac12 + 1 = 3/2",
            "mistakes": ["Нужно написать frac12 корректно"],
            "verdict": ["Оценка: 1/2."],
            "score_breakdown": [{"label": "Ошибка 1", "awarded": 1, "max": 2, "reason": "frac12 не оформлен"}],
            "feedback": "",
        }
        dummy_response = {"choices": [{"message": {"content": json.dumps(structured, ensure_ascii=False)}}]}

        from unittest.mock import patch

        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy_response
            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.submission.id]))

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("\\\\frac", data.get("recognized_solution") or "")
        sb = data.get("score_breakdown") or []
        self.assertTrue(sb)
        self.assertIn("\\\\frac", (sb[0].get("reason") or ""))
```

- [ ] **Step 2: Run to verify fails**

```bash
python manage.py test core.tests.test_ai_verdict_antifraud_and_breakdown -v 1
```

Expected: FAIL (пока нет новых полей/гейта/нормализации).

- [ ] **Step 3: Commit failing tests**

```bash
git add core/tests/test_ai_verdict_antifraud_and_breakdown.py
git commit -m "test: add antifraud and breakdown tests for ai verdict"
```

---

### Task 2: GREEN — добавить поля в Submission и миграцию

**Files:**
- Modify: [models.py](file:///workspace/core/models.py#L377-L416)
- Create: `/workspace/core/migrations/0055_submission_ai_photo_valid_and_breakdown.py`

- [ ] **Step 1: Update model (add fields)**

Добавить в `Submission` после текущих полей структурированного результата:

```python
    ai_photo_valid = models.BooleanField(null=True, blank=True, verbose_name="ИИ: фото валидно ли для этой задачи")
    ai_photo_valid_reason = models.TextField(blank=True, null=True, verbose_name="ИИ: причина невалидного фото")
    ai_recognition_confidence = models.FloatField(null=True, blank=True, verbose_name="ИИ: уверенность распознавания (0..1)")
    ai_score_breakdown_json = models.TextField(blank=True, null=True, verbose_name="ИИ: снятие баллов (JSON-массив объектов)")
```

- [ ] **Step 2: Create migration**

Создать миграцию с зависимостью от `0054_submission_ai_mistakes_json_and_more`.

```python
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0054_submission_ai_mistakes_json_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="ai_photo_valid",
            field=models.BooleanField(blank=True, null=True, verbose_name="ИИ: фото валидно ли для этой задачи"),
        ),
        migrations.AddField(
            model_name="submission",
            name="ai_photo_valid_reason",
            field=models.TextField(blank=True, null=True, verbose_name="ИИ: причина невалидного фото"),
        ),
        migrations.AddField(
            model_name="submission",
            name="ai_recognition_confidence",
            field=models.FloatField(blank=True, null=True, verbose_name="ИИ: уверенность распознавания (0..1)"),
        ),
        migrations.AddField(
            model_name="submission",
            name="ai_score_breakdown_json",
            field=models.TextField(blank=True, null=True, verbose_name="ИИ: снятие баллов (JSON-массив объектов)"),
        ),
    ]
```

- [ ] **Step 3: Run migrations**

```bash
python manage.py migrate
```

Expected: OK.

- [ ] **Step 4: Commit**

```bash
git add core/models.py core/migrations/0055_submission_ai_photo_valid_and_breakdown.py
git commit -m "feat: store ai photo validity and score breakdown"
```

---

### Task 3: GREEN — расширить api_verify_with_ai: промпт, парсинг, антифрод-гейт, нормализация LaTeX

**Files:**
- Modify: [views.py](file:///workspace/core/views.py#L5217-L5602)

- [ ] **Step 1: Update prompt to request new fields**

В промпте `api_verify_with_ai` добавить новые поля к списку возвращаемого JSON:

- `photo_valid`, `photo_valid_reason`, `recognition_confidence`, `score_breakdown`
- правило суммы breakdown = `primary_score`
- правило: при невалидном фото или низкой уверенности ставить 0 и не додумывать шаги

- [ ] **Step 2: Parse + normalize + validate**

После `parsed = pyjson.loads(...)` добавить:

```python
photo_valid = parsed.get("photo_valid")
if isinstance(photo_valid, str):
    photo_valid = photo_valid.strip().lower() in {"true", "1", "yes"}
if photo_valid is None:
    photo_valid = True

photo_valid_reason = str(parsed.get("photo_valid_reason") or "").strip()

try:
    recognition_confidence = float(parsed.get("recognition_confidence")) if parsed.get("recognition_confidence") is not None else None
except Exception:
    recognition_confidence = None

score_breakdown = parsed.get("score_breakdown") or []
if isinstance(score_breakdown, dict):
    score_breakdown = [score_breakdown]
if not isinstance(score_breakdown, list):
    score_breakdown = []

def _to_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

clean_breakdown = []
for item in score_breakdown:
    if not isinstance(item, dict):
        continue
    label = str(item.get("label") or "").strip()
    awarded = _to_int(item.get("awarded"), 0)
    mx = _to_int(item.get("max"), 0)
    reason = normalize_tex_in_feedback(str(item.get("reason") or "").strip())
    if not label and not reason:
        continue
    if mx < 0:
        mx = 0
    if awarded < 0:
        awarded = 0
    if awarded > mx:
        awarded = mx
    clean_breakdown.append({"label": label or "Критерий", "awarded": awarded, "max": mx, "reason": reason})

recognized_solution = normalize_tex_in_feedback(str(parsed.get("recognized_solution") or "").strip())
mistakes = [normalize_tex_in_feedback(str(x).strip()) for x in (mistakes or []) if str(x).strip()]
verdict = [normalize_tex_in_feedback(str(x).strip()) for x in (verdict or []) if str(x).strip()]
```

Сверка баллов:

```python
if clean_breakdown:
    sum_awarded = sum(int(x.get("awarded") or 0) for x in clean_breakdown)
    primary_score = sum_awarded
```

Антифрод-гейт:

```python
threshold = 0.35
force_zero = (photo_valid is False) or (recognition_confidence is not None and recognition_confidence < threshold)
if force_zero:
    primary_score = 0
    is_correct = False
    if not verdict:
        verdict = []
    if photo_valid is False and photo_valid_reason:
        verdict.insert(0, photo_valid_reason)
    if not any("перефото" in (v.lower()) or "загруз" in (v.lower()) for v in verdict):
        verdict.append("Загрузите корректное и читаемое фото решения этой задачи (без бликов, крупно, весь ход решения).")
```

Сохранение в `Submission`:

- новые поля: `ai_photo_valid`, `ai_photo_valid_reason`, `ai_recognition_confidence`, `ai_score_breakdown_json`
- гарантировать, что `ai_feedback` собирается fallback-логикой в правильном порядке и включает “Снятие баллов” при наличии breakdown

- [ ] **Step 3: Mirror changes in api_tutor_verify_with_ai**

Синхронизировать те же поля/логику в `api_tutor_verify_with_ai`, чтобы репетиторская перепроверка сохраняла и возвращала те же данные.

- [ ] **Step 4: Update clear-images endpoint**

В `api_clear_uploaded_photos` сбрасывать также:

- `ai_photo_valid`
- `ai_photo_valid_reason`
- `ai_recognition_confidence`
- `ai_score_breakdown_json`

- [ ] **Step 5: Run tests**

```bash
python manage.py test core.tests.test_ai_verdict_antifraud_and_breakdown -v 1
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/views.py
git commit -m "feat: structured ai verdict with antifraud and score breakdown"
```

---

### Task 4: GREEN — UI: секция “Снятие баллов” в деталях и в динамическом рендере

**Files:**
- Modify: [views.py](file:///workspace/core/views.py#L1481-L1603) — подготовка контекста `student_solve_assignment`
- Modify: [student_solve_assignment.html](file:///workspace/core/templates/core/student_solve_assignment.html#L179-L267)

- [ ] **Step 1: Parse breakdown JSON in student_solve_assignment context**

Добавить рядом с `ai_mistakes/ai_verdict`:

```python
try:
    task.saved_submission.ai_score_breakdown = (
        pyjson.loads(task.saved_submission.ai_score_breakdown_json)
        if task.saved_submission.ai_score_breakdown_json
        else []
    )
except Exception:
    task.saved_submission.ai_score_breakdown = []
```

- [ ] **Step 2: Add “Снятие баллов” section to detail block (server render)**

В `ai_detail_{{ task.id }}` добавить блок (между “Ошибки” и “Итоговый вердикт”):

- заголовок “Снятие баллов”
- список элементов `label: awarded/max` + `reason`

- [ ] **Step 3: Update verifyWithAI() JS to render breakdown**

В `hasStructured` учитывать `score_breakdown`.

Добавить секцию рендера:

```js
renderSection(wrap, 'Снятие баллов:', (body) => {
  const items = Array.isArray(data.score_breakdown) ? data.score_breakdown : [];
  if (!items.length) {
    const p = document.createElement('p');
    p.className = 'text-gray-500 italic';
    p.textContent = 'Разбивка баллов не получена.';
    body.appendChild(p);
    return;
  }
  const ul = document.createElement('ul');
  ul.className = 'space-y-2';
  items.forEach(it => {
    const li = document.createElement('li');
    const head = document.createElement('div');
    head.className = 'font-semibold text-gray-800';
    const label = (it && it.label) ? String(it.label) : 'Критерий';
    const awarded = (it && it.awarded != null) ? String(it.awarded) : '0';
    const max = (it && it.max != null) ? String(it.max) : '0';
    head.textContent = `${label}: ${awarded}/${max}`;
    li.appendChild(head);

    const reason = (it && it.reason) ? String(it.reason) : '';
    if (reason.trim()) {
      const r = document.createElement('div');
      r.className = 'text-gray-700 whitespace-pre-wrap';
      r.textContent = reason;
      li.appendChild(r);
    }
    ul.appendChild(li);
  });
  body.appendChild(ul);
});
```

Повторить то же для `wrap2` (обновление блока `ai_feedback_block_...`).

- [ ] **Step 4: Ensure math typesetting runs after render**

Сейчас вызывается `typesetMath(resultDiv)` и `typesetMath(blockEl)` — этого достаточно; убедиться, что секция breakdown попадает внутрь тех контейнеров.

- [ ] **Step 5: Run existing UI smoke tests**

```bash
python manage.py test core.tests.test_student_assignment_ai_full_report -v 1
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/views.py core/templates/core/student_solve_assignment.html
git commit -m "feat: show ai score breakdown in student ai verdict details"
```

---

### Task 5: GREEN — регресс-тест: breakdown отображается на странице (server render)

**Files:**
- Modify: `/workspace/core/tests/test_student_assignment_ai_full_report.py`

- [ ] **Step 1: Add a new test case**

```python
    def test_student_assignment_shows_score_breakdown_section_when_present(self):
        # setup same as existing test, but create submission with ai_score_breakdown_json
        Submission.objects.create(
            student=student,
            assignment=assignment,
            task=task,
            user_answer="",
            is_correct=False,
            primary_score=1,
            score=1,
            ai_feedback="Коротко",
            ai_recognized_solution="Распознано: x=1",
            ai_mistakes_json=json.dumps(["Ошибка 1"], ensure_ascii=False),
            ai_verdict_json=json.dumps(["Вердикт 1"], ensure_ascii=False),
            ai_score_breakdown_json=json.dumps([{"label": "К1", "awarded": 1, "max": 3, "reason": "Нет обоснования"}], ensure_ascii=False),
        )

        self.client.force_login(student)
        res = self.client.get(f"/student/assignment/{assignment.id}/")
        self.assertEqual(res.status_code, 200)

        html = res.content.decode("utf-8", errors="ignore")
        for needle in ["Снятие баллов", "К1", "1/3", "Нет обоснования"]:
            self.assertNotEqual(html.find(needle), -1, msg=f"Не найдено в HTML: {needle}")
```

- [ ] **Step 2: Run test**

```bash
python manage.py test core.tests.test_student_assignment_ai_full_report -v 1
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_student_assignment_ai_full_report.py
git commit -m "test: show score breakdown in student ai detail block"
```

---

## Plan Self-Review

- Spec coverage: добавлены новые поля (`photo_valid`, `recognition_confidence`, `score_breakdown`), серверный гейт (0 баллов), LaTeX-нормализация во всех секциях, UI-секция “Снятие баллов”.
- Placeholder scan: команды/код/пути файлов указаны, “TBD/TODO” отсутствуют.
- Type consistency: `score_breakdown` всегда массив объектов с `label/awarded/max/reason`, сериализация в `ai_score_breakdown_json`.

---

## Execution choice

Plan complete and saved to [2026-05-18-ai-verdict-latex-structured-report.md](file:///workspace/docs/superpowers/plans/2026-05-18-ai-verdict-latex-structured-report.md). Two execution options:

1. Subagent-Driven (recommended) — dispatch a fresh subagent per task, review between tasks
2. Inline Execution — execute tasks in this session using executing-plans

Which approach?

