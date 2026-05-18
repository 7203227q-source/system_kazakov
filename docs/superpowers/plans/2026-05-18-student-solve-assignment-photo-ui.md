# Student solve assignment: улучшение UI загрузки фото (2-я страница + удаление) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** После загрузки 1-й страницы фото на странице решения задания сразу становятся доступны действия “Удалить фото” и “Добавить/Заменить/Сфотографировать 2‑ю страницу”.

**Architecture:** Ничего не меняем в моделях/бэкенде — уже есть `image_url`/`image_url_2` и API `/api/submission/<id>/upload/`, `/api/submission/<id>/clear-images/`. Исправляем только шаблон `student_solve_assignment.html`: (1) после успешной загрузки 1-й страницы делаем reload, (2) добавляем отдельный camera-input для 2-й страницы с `capture="environment"` и обрабатываем его так же, как галерею.

**Tech Stack:** Django templates + vanilla JS (fetch/FormData).

---

## File map

**Modify**
- `/workspace/core/templates/core/student_solve_assignment.html`

**Create**
- `/workspace/core/tests/test_student_solve_assignment_second_page_camera_upload.py` (smoke-тест на наличие camera input для 2-й страницы)

---

### Task 1: UI — после загрузки 1-й страницы всегда показывать “Удалить” и “2-я страница”

**Files:**
- Modify: `/workspace/core/templates/core/student_solve_assignment.html` (блок `handleFile()` в ветке “Ожидание загрузки”)

- [ ] **Step 1: Write failing test (template-level smoke check)**
  - Этот тест “на поведение UI” через JS в браузере не гоняем, но фиксируем контракт: в шаблоне должен быть `location.reload()` после успешного upload 1-й страницы.

```python
# /workspace/core/tests/test_student_solve_assignment_second_page_camera_upload.py
import pytest
from django.urls import reverse

from core.models import Assignment, Task, TaskType, User

@pytest.mark.django_db
def test_student_solve_assignment_first_page_upload_reloads_page(client):
    student = User.objects.create_user(username="s@test.com", password="pw", role="student")
    client.force_login(student)

    tt = TaskType.objects.create(name="Part2", number=1, max_points=2, is_extended_answer=True)
    t = Task.objects.create(title="T", correct_answer="1", task_type=tt, exam_points=2, content="x")
    a = Assignment.objects.create(title="A", student=student, is_draft=False, is_completed=False)
    a.tasks.add(t)

    url = reverse("student_solve_assignment", args=[a.id])
    html = client.get(url).content.decode("utf-8")
    assert "location.reload()" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest -q core/tests/test_student_solve_assignment_second_page_camera_upload.py::test_student_solve_assignment_first_page_upload_reloads_page
```
Expected: FAIL (до правки `location.reload()` нет в ветке upload 1-й страницы).

- [ ] **Step 3: Minimal implementation**
  - В `handleFile()` после успешного `fetch(uploadUrl, ...)` вместо подмены HTML на “упрощённый блок” делаем:
    - оставить статус “Загружено”
    - вызвать `location.reload()` (как уже сделано для 2-й страницы), чтобы отрисовалась серверная ветка “Фото уже загружено” (там есть и удаление, и 2-я страница).

- [ ] **Step 4: Run tests**

Run:
```bash
pytest -q core/tests/test_student_solve_assignment_second_page_camera_upload.py::test_student_solve_assignment_first_page_upload_reloads_page
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/templates/core/student_solve_assignment.html core/tests/test_student_solve_assignment_second_page_camera_upload.py
git commit -m "fix(student): reload after first photo upload to show delete/2nd page actions"
```

---

### Task 2: UI — “Сделать фото 2‑й страницы” (capture=environment)

**Files:**
- Modify: `/workspace/core/templates/core/student_solve_assignment.html` (ветка `task.saved_submission.image_url`)
- Modify: `/workspace/core/tests/test_student_solve_assignment_second_page_camera_upload.py`

- [ ] **Step 1: Write failing test**
  - Проверяем, что на странице присутствует input для камеры 2-й страницы с `capture="environment"` и что он называется ожидаемо (например `camera_file2_`).

```python
@pytest.mark.django_db
def test_student_solve_assignment_has_second_page_camera_input(client):
    student = User.objects.create_user(username="s2@test.com", password="pw", role="student")
    client.force_login(student)

    tt = TaskType.objects.create(name="Part2", number=1, max_points=2, is_extended_answer=True)
    t = Task.objects.create(title="T", correct_answer="1", task_type=tt, exam_points=2, content="x")
    a = Assignment.objects.create(title="A", student=student, is_draft=False, is_completed=False)
    a.tasks.add(t)

    html = client.get(reverse("student_solve_assignment", args=[a.id])).content.decode("utf-8")
    assert "camera_file2_" in html
    assert 'capture="environment"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest -q core/tests/test_student_solve_assignment_second_page_camera_upload.py::test_student_solve_assignment_has_second_page_camera_input
```
Expected: FAIL

- [ ] **Step 3: Minimal implementation**
  - В ветке “Фото уже загружено” добавить:
    - скрытый input: `<input type="file" id="camera_file2_{{ task.id }}" class="hidden" accept="image/*" capture="environment">`
    - кнопку “Сделать фото 2‑й страницы” рядом с “Добавить/Заменить 2‑ю страницу”
  - В JS (где сейчас `const input2 = gallery_file2_...`) добавить `cameraInput2` и повесить на него такой же обработчик `handleSecond(file)`.

- [ ] **Step 4: Run tests**

Run:
```bash
pytest -q core/tests/test_student_solve_assignment_second_page_camera_upload.py
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/templates/core/student_solve_assignment.html core/tests/test_student_solve_assignment_second_page_camera_upload.py
git commit -m "feat(student): add camera capture for second page upload"
```

---

### Task 3: Regression sweep

**Files:**
- None (run full relevant suite)

- [ ] **Step 1: Run existing related tests**

Run:
```bash
pytest -q core/tests/test_submission_clear_images.py core/tests/test_submission_upload_second_page.py core/tests/test_mobile_upload_second_page.py core/tests/test_student_solve_assignment_desktop_upload.py
```
Expected: PASS

