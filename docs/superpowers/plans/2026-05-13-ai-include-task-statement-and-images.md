# AI Photo Grading: Include Task Statement & Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В ИИ-проверке фото решения добавить в промпт текст условия (plain text) и прикреплять все изображения из условия, чтобы корректнее проверять задачи с рисунками/графиками.

**Architecture:** В `api_verify_with_ai` извлекаем HTML условия через `task.get_content_for_theme()`, парсим `BeautifulSoup` для получения plain text и списка `img src`, фильтруем URL, конвертируем относительные ссылки в абсолютные через `request.build_absolute_uri`, затем добавляем эти данные в `messages[...].content` (text + image_url entries). То же применяется к `?mode=compare`.

**Tech Stack:** Django views/tests, bs4 (уже используется в тестах), OpenRouter chat-completions payload.

---

## Files (map)

**Modify**
- `/workspace/core/views.py` — `api_verify_with_ai` (добавить условие/картинки)
- `/workspace/core/tests/test_ai_verify_compare_mode.py` — расширить тест compare для проверки payload

**Create**
- `/workspace/core/tests/test_ai_verify_prompt_includes_task_assets.py`

---

### Task 1: RED — тест: payload включает «Условие:» и картинки из условия (и в compare-режиме)

**Files:**
- Create: `/workspace/core/tests/test_ai_verify_prompt_includes_task_assets.py`

- [ ] **Step 1: Write failing test**

```python
import json
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, OpenRouterModel, Subject, SubjectAIConfig, Submission, Task, TaskType, TaskVariant, Topic, User


class AIVerifyPromptIncludesTaskAssetsTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.subject = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=self.subject, name="ОГЭ", year=2026, is_active=True)
        tt = TaskType.objects.create(exam_format=ef, number=20, name="Тип 20", max_points=2)
        topic = Topic.objects.create(subject=self.subject, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt, correct_answer="1", difficulty=10, exam_points=2)
        TaskVariant.objects.create(
            task=self.task,
            theme="classic",
            content="<p>Условие: построй график</p><img src=\"/media/a.png\"><img src=\"https://math-ege.sdamgia.ru/img/b.png\">",
            solution="",
        )

        self.sub = Submission.objects.create(student=self.student, task=self.task, is_correct=None)
        self.sub.image_url = SimpleUploadedFile("a.jpg", b"fake", content_type="image/jpeg")
        self.sub.save()

        self.m = OpenRouterModel.objects.create(code="m1", label="M1", capabilities="vision", is_active=True)
        SubjectAIConfig.objects.create(subject=self.subject, photo_analysis_model=self.m)

    def test_prompt_text_and_images_are_attached(self):
        os.environ["OPENROUTER_API_KEY"] = "test"

        dummy = {"choices": [{"message": {"content": json.dumps({"primary_score": 1, "is_correct": False, "feedback": "ok"})}}]}

        from unittest.mock import patch
        with patch("core.views.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = dummy

            self.client.force_login(self.student)
            res = self.client.post(reverse("api_verify_with_ai", args=[self.sub.id]))

        self.assertEqual(res.status_code, 200)
        sent_payload = post.call_args.kwargs["json"]
        user_msg = next(m for m in sent_payload["messages"] if m["role"] == "user")
        content = user_msg["content"]
        text = next(p["text"] for p in content if p["type"] == "text")
        self.assertIn("Условие:", text)
        imgs = [p["image_url"]["url"] for p in content if p["type"] == "image_url"]
        self.assertTrue(any(u.endswith("/media/a.png") or "/media/a.png" in u for u in imgs))
        self.assertTrue(any("math-ege.sdamgia.ru" in u for u in imgs))
```

- [ ] **Step 2: Run to verify fails**

```bash
python manage.py test core.tests.test_ai_verify_prompt_includes_task_assets -v 1
```
Expected: FAIL (условие/картинки ещё не добавляются).

- [ ] **Step 3: Commit failing test**

```bash
git add core/tests/test_ai_verify_prompt_includes_task_assets.py
git commit -m "test: include task statement and images in AI prompt"
```

---

### Task 2: GREEN — реализовать извлечение текста и картинок и добавление в payload

**Files:**
- Modify: `/workspace/core/views.py`
- Test: `/workspace/core/tests/test_ai_verify_prompt_includes_task_assets.py`

- [ ] **Step 1: Extract plain text**
В `api_verify_with_ai` получить HTML условия:
`task_html = task.get_content_for_theme()` и извлечь текст через `BeautifulSoup`:
- удалить `script/style/noscript`
- `get_text(" ", strip=True)` и нормализовать пробелы

- [ ] **Step 2: Extract & filter images**
Из того же HTML собрать все `img src`/`data-src`/`data-original`, отфильтровать:
- запретить `data:`/`javascript:`/`file:`
- разрешить `/media/...`, `/proxy-image/...`
- разрешить `http/https` только если host заканчивается на `sdamgia.ru`
Для относительных URL конвертировать в абсолютные `request.build_absolute_uri(url)`.
Дедупликация по порядку.

- [ ] **Step 3: Attach to OpenRouter user content**
Сформировать `user_content`:
- 1 элемент text: текущий промпт + `\n\nУсловие:\n{plain_text}`
- далее `image_url` фото решения (data_url)
- далее `image_url` для всех картинок условия (абсолютные URL)

Применить как для обычного потока, так и для `mode == "compare"`.

- [ ] **Step 4: Run tests**

```bash
python manage.py test core.tests.test_ai_verify_prompt_includes_task_assets -v 1
python manage.py test core.tests.test_ai_verify_compare_mode -v 1
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/views.py
git commit -m "feat: include task statement and images in AI grading prompt"
```

---

### Task 3: Full regression + push

- [ ] **Step 1: Run full suite**

```bash
python manage.py test core.tests -v 1
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

