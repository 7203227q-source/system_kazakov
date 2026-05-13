# Remove “5 models” compare mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать функциональность “Проверить 5 моделями” из продукта (UI + backend), оставив настройки сравнения в админке как неиспользуемые.

**Architecture:** Считаем `mode=compare` неподдерживаемым: endpoint возвращает 400 с понятной ошибкой. В UI убираем кнопку и JS-логику compare, чтобы пользователь не мог вызвать режим.

**Tech Stack:** Django (views/templates), existing tests.

---

## Files to Touch

- Modify: `/workspace/core/views.py` (`api_verify_with_ai`)
- Modify: `/workspace/core/templates/core/student_solve_assignment.html`
- Modify: `/workspace/core/tests/test_ai_verify_compare_mode.py` (или другой тест compare, если есть)

---

### Task 1: RED — тест на запрет compare mode

**Files:**
- Modify: existing compare-mode test

- [ ] **Step 1: Update test to expect 400**
  - Запрос: `POST /api/submission/<id>/verify/?mode=compare`
  - Ожидаем: `400` и JSON `{error: "compare_not_supported"}`

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python manage.py test core.tests.test_ai_verify_compare_mode -v 1
```

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_ai_verify_compare_mode.py
git commit -m "test: compare mode is not supported"
```

---

### Task 2: GREEN — backend: отключить compare mode

**Files:**
- Modify: `/workspace/core/views.py`

- [ ] **Step 1: Add early guard**

В `api_verify_with_ai`:
```python
if request.GET.get("mode") == "compare":
    return JsonResponse({"error": "compare_not_supported"}, status=400)
```

- [ ] **Step 2: Run test**

```bash
python manage.py test core.tests.test_ai_verify_compare_mode -v 1
```

- [ ] **Step 3: Commit**

```bash
git add core/views.py
git commit -m "feat: disable compare mode in ai verify endpoint"
```

---

### Task 3: GREEN — UI: убрать кнопку и JS compare

**Files:**
- Modify: `/workspace/core/templates/core/student_solve_assignment.html`

- [ ] **Step 1: Remove compare button in server-rendered template**
- [ ] **Step 2: Remove compare button in dynamically-rendered card template**
- [ ] **Step 3: Remove `verifyWithAICompare` and `renderCompareResults` JS if unused**
- [ ] **Step 4: Run smoke tests**

```bash
python manage.py test core.tests -v 1
```

- [ ] **Step 5: Commit**

```bash
git add core/templates/core/student_solve_assignment.html
git commit -m "feat: remove compare mode UI"
```

---

### Task 4: Full test suite + push

- [ ] **Step 1: Run full suite**

```bash
python manage.py test core.tests -v 1
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

