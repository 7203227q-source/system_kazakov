# AI Check for Second Part Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ограничить ИИ-проверку фото только задачами 2 части (exam_points > 1) и убрать фейковый fallback: если OpenRouter не настроен — возвращать ошибку без изменения `Submission`.

**Architecture:** В `api_verify_with_ai` добавляем guard по `task.exam_points`. Убираем ветку заглушки и вместо неё возвращаем 400 с понятным сообщением. В шаблоне `student_solve_assignment.html` скрываем кнопку “Проверить через ИИ” для задач не 2 части и улучшаем обработку ошибок `verifyWithAI()`.

**Tech Stack:** Django views/templates, Django TestCase.

---

## Files (map)

**Modify**
- `/workspace/core/views.py` — `api_verify_with_ai`
- `/workspace/core/templates/core/student_solve_assignment.html` — условия показа кнопки и обработка ошибок

**Create**
- `/workspace/core/tests/test_ai_verify_second_part_only.py`

---

### Task 1: RED — тест: ИИ-проверка запрещена для exam_points == 1

**Files:**
- Create: `/workspace/core/tests/test_ai_verify_second_part_only.py`

- [ ] **Step 1: Write failing test**

```python
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Submission, Subject, Task, TaskType, Topic, User


class AIVerifySecondPartOnlyTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        subj = Subject.objects.create(name="Математика")
        ef = ExamFormat.objects.create(subject=subj, name="ОГЭ математика", year=2026, is_active=True)
        tt1 = TaskType.objects.create(exam_format=ef, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subj, name="T")
        self.task = Task.objects.create(topic=topic, task_type=tt1, correct_answer="1", difficulty=10, exam_points=1)

        self.sub = Submission.objects.create(student=self.student, task=self.task, is_correct=None)
        self.sub.image_url = SimpleUploadedFile("a.jpg", b"fake", content_type="image/jpeg")
        self.sub.save()

    def test_verify_rejected_for_test_part(self):
        self.client.login(username="s", password="pass")
        res = self.client.post(reverse("api_verify_with_ai", args=[self.sub.id]))
        self.assertEqual(res.status_code, 400)
        self.sub.refresh_from_db()
        self.assertIsNone(self.sub.primary_score)
        self.assertIsNone(self.sub.is_correct)
        self.assertIsNone(self.sub.ai_feedback)
```

- [ ] **Step 2: Run to verify fails**

```bash
python manage.py test core.tests.test_ai_verify_second_part_only -v 1
```
Expected: FAIL (сейчас endpoint позволяет exam_points==1 и может записывать результат).

- [ ] **Step 3: Commit failing test**

```bash
git add core/tests/test_ai_verify_second_part_only.py
git commit -m "test: ai verify only for second part tasks"
```

---

### Task 2: RED — тест: если ключ/модель не настроены, возвращать 400 и не менять Submission

**Files:**
- Modify: `/workspace/core/tests/test_ai_verify_second_part_only.py`

- [ ] **Step 1: Add failing test**

```python
    def test_verify_requires_openrouter_config(self):
        subj = self.task.topic.subject
        ef = self.task.task_type.exam_format
        tt2 = TaskType.objects.create(exam_format=ef, number=20, name="Тип 20", max_points=2)
        t2 = Task.objects.create(topic=self.task.topic, task_type=tt2, correct_answer="1", difficulty=10, exam_points=2)
        sub2 = Submission.objects.create(student=self.student, task=t2, is_correct=None)
        sub2.image_url = SimpleUploadedFile("b.jpg", b"fake", content_type="image/jpeg")
        sub2.save()

        os.environ.pop("OPENROUTER_API_KEY", None)

        self.client.login(username="s", password="pass")
        res = self.client.post(reverse("api_verify_with_ai", args=[sub2.id]))
        self.assertEqual(res.status_code, 400)
        sub2.refresh_from_db()
        self.assertIsNone(sub2.primary_score)
        self.assertIsNone(sub2.is_correct)
        self.assertIsNone(sub2.ai_feedback)
```

- [ ] **Step 2: Run to verify fails**

```bash
python manage.py test core.tests.test_ai_verify_second_part_only -v 1
```
Expected: FAIL (сейчас есть fallback, который пишет результат).

- [ ] **Step 3: Commit failing test**

```bash
git add core/tests/test_ai_verify_second_part_only.py
git commit -m "test: ai verify requires openrouter config"
```

---

### Task 3: GREEN — api_verify_with_ai: запрет для 1 части + убрать fallback

**Files:**
- Modify: `/workspace/core/views.py`
- Test: `/workspace/core/tests/test_ai_verify_second_part_only.py`

- [ ] **Step 1: Add guard exam_points**
В `api_verify_with_ai` после загрузки `task`:

```python
    if int(task.exam_points or 0) <= 1:
        return JsonResponse({'error': 'only_second_part'}, status=400)
```

- [ ] **Step 2: Remove fallback**
Если `api_key` пустой или `model` пустой:
- вернуть `JsonResponse({'error': 'ai_not_configured'}, status=400)`
- НЕ писать в `Submission`

И аналогично, если OpenRouter вернул не-200/парсинг упал — тоже вернуть `400` с `error: 'ai_failed'` (без записи результата).

- [ ] **Step 3: Run tests**

```bash
python manage.py test core.tests.test_ai_verify_second_part_only -v 1
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add core/views.py
git commit -m "fix: restrict ai verify to second part and require config"
```

---

### Task 4: GREEN — student_solve_assignment UI: кнопка только для 2 части + обработка ошибок

**Files:**
- Modify: `/workspace/core/templates/core/student_solve_assignment.html`

- [ ] **Step 1: Hide button for test part**
В местах, где показывается кнопка “Проверить решение через ИИ”, обернуть условием:
`{% if task.exam_points|default:0 > 1 %}`

- [ ] **Step 2: Better JS error handling**
В `verifyWithAI()`:
- если `!response.ok` — показать `data.error` человеко-читаемо и вернуть кнопку в исходное состояние.

- [ ] **Step 3: Commit**

```bash
git add core/templates/core/student_solve_assignment.html
git commit -m "feat: show ai verify button only for second part"
```

---

### Task 5: Full regression + push

- [ ] **Step 1: Run full suite**

```bash
python manage.py test core.tests -v 1
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

