# AI Compare 5 Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить временный режим сравнения ИИ-проверки фото решения сразу 5 моделями (настраиваются в админке), с показом результатов ученику и без сохранения в БД.

**Architecture:** Расширяем `SubjectAIConfig` на 5 “compare”-моделей. В `api_verify_with_ai` добавляем режим `?mode=compare` — делаем 5 вызовов OpenRouter, агрегируем результаты и возвращаем в JSON, не меняя `Submission`. В UI ученика добавляем кнопку “Проверить 5 моделями” и вывод аккордеоном.

**Tech Stack:** Django models/migrations, Django views, Django templates/JS, Django TestCase.

---

## Files (map)

**Modify**
- `/workspace/core/models.py` — `SubjectAIConfig` (5 новых FK)
- `/workspace/core/migrations/` — миграция
- `/workspace/core/views.py` — `api_verify_with_ai` compare-режим
- `/workspace/core/templates/core/admin_system.html` — 5 select для предмета
- `/workspace/core/views.py` — `admin_system` сохранение полей
- `/workspace/core/templates/core/student_solve_assignment.html` — кнопка + UI результатов

**Create**
- `/workspace/core/tests/test_ai_verify_compare_mode.py`

---

### Task 1: RED — тест compare-режима (5 результатов, без изменения Submission)

**Files:**
- Create: `/workspace/core/tests/test_ai_verify_compare_mode.py`

- [ ] **Step 1: Write failing test**

```python
import json
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, OpenRouterModel, Subject, SubjectAIConfig, Submission, Task, TaskType, Topic, User


class AIVerifyCompareModeTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=20, name="Тип 20", max_points=2)
        topic = Topic.objects.create(subject=self.subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)

        self.sub = Submission.objects.create(student=self.student, task=self.task, is_correct=None)
        self.sub.image_url = SimpleUploadedFile("a.jpg", b"fake", content_type="image/jpeg")
        self.sub.save()

        # 5 моделей для сравнения
        self.m1 = OpenRouterModel.objects.create(code="m1", label="M1", capabilities="vision", is_active=True)
        self.m2 = OpenRouterModel.objects.create(code="m2", label="M2", capabilities="vision", is_active=True)
        self.m3 = OpenRouterModel.objects.create(code="m3", label="M3", capabilities="vision", is_active=True)
        self.m4 = OpenRouterModel.objects.create(code="m4", label="M4", capabilities="vision", is_active=True)
        self.m5 = OpenRouterModel.objects.create(code="m5", label="M5", capabilities="vision", is_active=True)
        SubjectAIConfig.objects.create(
            subject=self.subject,
            photo_analysis_model=self.m1,
            photo_compare_model_1=self.m1,
            photo_compare_model_2=self.m2,
            photo_compare_model_3=self.m3,
            photo_compare_model_4=self.m4,
            photo_compare_model_5=self.m5,
        )

    def test_compare_returns_5_results_and_does_not_mutate_submission(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        dummy = {"choices": [{"message": {"content": json.dumps({"primary_score": 1, "is_correct": False, "feedback": "ok"})}}]}

        from unittest.mock import patch
        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy

            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.sub.id]) + "?mode=compare")

        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["mode"], "compare")
        self.assertEqual(len(payload["results"]), 5)
        self.assertEqual(post.call_count, 5)

        self.sub.refresh_from_db()
        self.assertIsNone(self.sub.primary_score)
        self.assertIsNone(self.sub.ai_feedback)
        self.assertIsNone(self.sub.is_correct)
```

- [ ] **Step 2: Run to verify fails**

```bash
python manage.py test core.tests.test_ai_verify_compare_mode -v 1
```
Expected: FAIL (нет полей compare + нет режима compare).

- [ ] **Step 3: Commit failing test**

```bash
git add core/tests/test_ai_verify_compare_mode.py
git commit -m "test: compare ai verify across 5 models"
```

---

### Task 2: GREEN — добавить 5 полей compare в SubjectAIConfig + миграция

**Files:**
- Modify: `/workspace/core/models.py`
- Create: `/workspace/core/migrations/00xx_subject_ai_compare_models.py`
- Test: `/workspace/core/tests/test_ai_verify_compare_mode.py`

- [ ] **Step 1: Update model**

Добавить в `SubjectAIConfig`:

```python
    photo_compare_model_1 = models.ForeignKey(OpenRouterModel, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    photo_compare_model_2 = models.ForeignKey(OpenRouterModel, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    photo_compare_model_3 = models.ForeignKey(OpenRouterModel, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    photo_compare_model_4 = models.ForeignKey(OpenRouterModel, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    photo_compare_model_5 = models.ForeignKey(OpenRouterModel, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
```

- [ ] **Step 2: Create migration**
Сгенерировать миграцию `makemigrations core`.

- [ ] **Step 3: Run test**

```bash
python manage.py test core.tests.test_ai_verify_compare_mode -v 1
```
Expected: FAIL (режима compare ещё нет).

- [ ] **Step 4: Commit**

```bash
git add core/models.py core/migrations
git commit -m "feat: add 5 compare models to SubjectAIConfig"
```

---

### Task 3: GREEN — admin_system: добавить 5 селектов и сохранение

**Files:**
- Modify: `/workspace/core/templates/core/admin_system.html`
- Modify: `/workspace/core/views.py` (обработка `save_subject_ai_configs`)

- [ ] **Step 1: Template fields**
Добавить 5 `<select>` в таблицу предметов рядом с “Анализ фото” или отдельной колонкой “Сравнение (5)”:
`subject_<id>_photo_compare_model_1..5` с тем же списком `featured_models`/`other_models`.

- [ ] **Step 2: Save logic**
В обработке `save_subject_ai_configs` прочитать эти 5 полей и записать в `SubjectAIConfig`.

- [ ] **Step 3: Commit**

```bash
git add core/templates/core/admin_system.html core/views.py
git commit -m "feat: configure 5 compare models per subject"
```

---

### Task 4: GREEN — api_verify_with_ai: режим ?mode=compare

**Files:**
- Modify: `/workspace/core/views.py`
- Test: `/workspace/core/tests/test_ai_verify_compare_mode.py`

- [ ] **Step 1: Branch by mode**
В начале `api_verify_with_ai`:
- `mode = request.GET.get("mode")`
- если `mode == "compare"`:
  - те же проверки (auth, image_url, 2 часть, key, config subject)
  - взять 5 compare моделей, если не все заданы → `400 {error: "compare_models_not_configured"}`
  - сделать 5 запросов OpenRouter (последовательно), для каждого:
    - подставить `model=<code>`
    - распарсить JSON как в обычном потоке
    - добавить в `results`
  - вернуть JSON с `mode`, `max_points`, `results`
  - НЕ сохранять в `Submission`

- [ ] **Step 2: Run test**

```bash
python manage.py test core.tests.test_ai_verify_compare_mode -v 1
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add core/views.py
git commit -m "feat: compare ai verify across 5 models"
```

---

### Task 5: GREEN — UI ученика: кнопка и аккордеон результатов

**Files:**
- Modify: `/workspace/core/templates/core/student_solve_assignment.html`

- [ ] **Step 1: Add button**
В блоке “Решение загружено” добавить кнопку:
- `Проверить 5 моделями` (рядом/ниже основной)
- показывать только если `task.exam_points_effective > 1`

- [ ] **Step 2: JS function**
Добавить `verifyWithAICompare(submissionId, taskId)`:
- POST `/api/submission/<id>/verify/?mode=compare`
- отрисовать блок результатов как аккордеон (5 секций)

- [ ] **Step 3: Commit**

```bash
git add core/templates/core/student_solve_assignment.html
git commit -m "feat: show compare results for 5 models"
```

---

### Task 6: Full regression + push

- [ ] **Step 1: Run full suite**

```bash
python manage.py test core.tests -v 1
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

