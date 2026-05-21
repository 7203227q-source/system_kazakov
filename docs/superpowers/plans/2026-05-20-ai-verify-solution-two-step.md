# Two-Step AI Photo Verification (Use Reference Solution) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AI photo verification more accurate by first extracting what’s visible in the student’s photo, then grading against the task’s reference solution (when available).

**Architecture:** Split verification into 2 OpenRouter calls: (1) vision recognition-only response (photo validity + recognized_solution), (2) text-only grading call using recognized_solution + task statement + reference solution. Keep existing API response shape to avoid frontend changes.

**Tech Stack:** Django views, OpenRouter chat completions API, BeautifulSoup HTML→text extraction, existing Submission AI fields.

---

## File Map

**Modify**
- [views.py](file:///workspace/core/views.py): `api_verify_with_ai`, `api_tutor_verify_with_ai` to run the 2-step flow and select `solution_check_model` for step 2.
- [test_submission_verify_openrouter_structured.py](file:///workspace/core/tests/test_submission_verify_openrouter_structured.py): update mocks for 2 sequential OpenRouter calls.
- [test_submission_verify_openrouter.py](file:///workspace/core/tests/test_submission_verify_openrouter.py): update mocks for 2 sequential calls (and keep 1-call fallback path).
- [test_submission_verify_openrouter_two_images.py](file:///workspace/core/tests/test_submission_verify_openrouter_two_images.py): update mocks for 2 sequential calls with 2 images.

---

## Task 1: Add 2-step recognition → grading flow (student endpoint)

**Files:**
- Modify: [views.py](file:///workspace/core/views.py) (`api_verify_with_ai`)
- Test: [test_submission_verify_openrouter_structured.py](file:///workspace/core/tests/test_submission_verify_openrouter_structured.py)

- [ ] **Step 1: Write/adjust failing test (structured) for 2 OpenRouter calls**

Update `test_verify_saves_structured_fields` to mock 2 responses:
1) recognition JSON (no scoring),
2) grading JSON (score + mistakes + breakdown + verdict).

Example patch sketch for the test (adapt exact import paths already used in the file):

```python
from unittest.mock import patch

recognition = {
    "photo_valid": True,
    "photo_valid_reason": "",
    "recognition_confidence": 0.8,
    "recognized_solution": "1) Перенёс влево\n2) Сократил",
}
grading = {
    "primary_score": 1,
    "score_breakdown": [{"label": "К1", "awarded": 1, "max": 2, "reason": "Потерян знак"}],
    "mistakes": ["Потерян знак минус"],
    "verdict": ["Оценка: 1/2.", "Неуверенность распознавания: низкая."],
    "feedback": "",
}

dummy_res_1 = {"choices": [{"message": {"content": json.dumps(recognition, ensure_ascii=False)}}]}
dummy_res_2 = {"choices": [{"message": {"content": json.dumps(grading, ensure_ascii=False)}}]}

with patch("core.views.requests.post") as post:
    post.return_value.status_code = 200
    post.side_effect = [
        type("R", (), {"status_code": 200, "json": lambda self=None: dummy_res_1})(),
        type("R", (), {"status_code": 200, "json": lambda self=None: dummy_res_2})(),
    ]
    ...
```

Expected: test fails until implementation performs 2 calls and saves fields.

- [ ] **Step 2: Implement step 1 (recognition-only) prompt and parsing in `api_verify_with_ai`**

In [views.py](file:///workspace/core/views.py), inside `api_verify_with_ai`:
- Keep current extraction of `task_text`, `task_image_data_urls`, and conversion of `submission.image_url` to `data_url`.
- Replace the current “single-step grading” prompt with a “recognition-only” prompt and parse response to get:
  - `photo_valid`, `photo_valid_reason`, `recognition_confidence`, `recognized_solution`.

Recognition prompt shape (keep “JSON only” constraint):

```python
recognition_prompt = (
    "Проанализируй фото решения ученика.\n"
    "Твоя задача — ТОЛЬКО распознать, что написано на фото, и проверить, относится ли фото к этой задаче.\n"
    "\n"
    "Верни ТОЛЬКО JSON (без markdown) со следующими полями:\n"
    "- photo_valid: boolean\n"
    "- photo_valid_reason: string\n"
    "- recognition_confidence: number (0..1)\n"
    "- recognized_solution: string (что именно видно на фото; допускаются переносы строк)\n"
    "\n"
    "ВАЖНО:\n"
    "- Не выставляй баллы и не оценивай правильность.\n"
    "- Описывай ТОЛЬКО то, что реально видно на фото.\n"
    "- Если часть не читается — помечай: [неразборчиво]/[не видно].\n"
    "- Не додумывай шаги. Любые предположения помечай как «ПРЕДПОЛОЖЕНИЕ: ...».\n"
    "\n"
    "Формулы в LaTeX: $...$ / $$...$$. Так как ответ JSON — экранируй обратные слэши (двойной обратный слэш)."
)
if task_text:
    recognition_prompt = f"{recognition_prompt}\n\nУсловие:\n{task_text}"
```

Then send messages exactly like current code does (system: JSON only), but keep images in `user_content`.

Parsing:
- Reuse the existing `_repair_json_for_latex` and json-extraction fallback.
- Create a small local validator in the view (or a helper function near `parse_ai_photo_verdict`) to normalize recognition fields:

```python
photo_valid = bool(parsed.get("photo_valid", True))
photo_valid_reason = str(parsed.get("photo_valid_reason") or "").strip()
recognized_solution = normalize_tex_in_feedback(str(parsed.get("recognized_solution") or "").strip())
try:
    recognition_confidence = float(parsed.get("recognition_confidence"))
except Exception:
    recognition_confidence = None
```

- If `photo_valid is False` OR `recognition_confidence is not None and recognition_confidence < 0.35`:
  - Force `primary_score = 0`, `is_correct = False`, clear breakdown/mistakes/verdict,
  - Save recognition fields to submission (`ai_recognized_solution`, `ai_photo_valid*`, `ai_recognition_confidence`) and return the same JSON as now (with `primary_score=0`).

- [ ] **Step 3: Implement step 2 (grading against reference solution)**

Still in `api_verify_with_ai`, after successful recognition (photo valid & confidence ok):
- Fetch reference solution:

```python
solution_html = ""
try:
    solution_html = task.get_solution_for_theme(theme) or ""
except Exception:
    solution_html = ""
```

- If `solution_html.strip()` is empty: fallback to the current single-step flow (keep backward compatibility).
- Else:
  - Convert `solution_html` → `solution_text` similarly to how `task_text` is extracted (strip scripts/styles and get clean text):

```python
solution_soup = BeautifulSoup(solution_html, "html.parser")
for t in solution_soup(["script", "style", "noscript"]):
    t.decompose()
solution_text = re.sub(r"\s+", " ", solution_soup.get_text(" ", strip=True) or "").strip()
solution_text = solution_text.replace("\\", "\\\\")
```

  - Select step-2 model:
    - prefer `SubjectAIConfig.solution_check_model.code`,
    - fallback to `SubjectAIConfig.photo_analysis_model.code`.

  - Build grading prompt that explicitly forbids inventing missing steps and instructs to grade *only* using `recognized_solution`:

```python
grading_prompt = (
    "Ты проверяешь решение ученика по распознанному тексту (не по фото).\n"
    f"Максимум баллов: {max_points}.\n"
    "\n"
    "Дано:\n"
    "- Условие задачи\n"
    "- Эталонное решение\n"
    "- Распознанное решение ученика (может быть неполным)\n"
    "\n"
    "Оцени, насколько распознанное решение соответствует эталону.\n"
    "ВАЖНО:\n"
    "- НЕ додумывай шаги, которых нет в распознанном решении.\n"
    "- Если распознанное решение неполное/не хватает данных — снизь балл и явно укажи, чего не хватает.\n"
    "\n"
    "Верни ТОЛЬКО JSON (без markdown):\n"
    "- primary_score: number (целое 0..max)\n"
    "- score_breakdown: array of objects (label, awarded, max, reason) (сумма awarded = primary_score)\n"
    "- mistakes: array of strings\n"
    "- verdict: array of strings (каждый элемент — абзац; включи пункт «Неуверенность распознавания: ...»)\n"
    "- feedback: string (опционально)\n"
    "\n"
    "Формулы в LaTeX: $...$ / $$...$$. В JSON экранируй обратные слэши."
)
```

  - Compose a text-only message content:

```python
grading_payload = (
    f"{grading_prompt}\n\n"
    f"Условие:\n{task_text}\n\n"
    f"Эталонное решение:\n{solution_text}\n\n"
    f"Распознанное решение ученика:\n{recognized_solution}"
)
```

  - Call OpenRouter with `messages=[{"role":"system",...}, {"role":"user","content": grading_payload}]` (no images).
  - Parse JSON (reuse `_repair_json_for_latex`).
  - Validate:
    - clamp `primary_score` to `0..max_points`,
    - `mistakes` list normalization,
    - `score_breakdown` normalization and sum rule (if breakdown provided, recompute score),
    - ensure verdict contains the “Неуверенность…” line (if not, add).

  - Save to `Submission` the same fields as current flow (`primary_score`, `is_correct`, `ai_feedback`, `ai_mistakes_json`, `ai_verdict_json`, `ai_score_breakdown_json`) plus the recognition fields from step 1.

Note: keep the existing response shape returned by `api_verify_with_ai`, including `solution_html` for the UI.

- [ ] **Step 4: Run tests**

Run:
```bash
pytest -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/tests/test_submission_verify_openrouter_structured.py
git commit -m "feat: add 2-step AI photo verify with reference solution"
```

---

## Task 2: Apply same 2-step logic to tutor endpoint

**Files:**
- Modify: [views.py](file:///workspace/core/views.py) (`api_tutor_verify_with_ai`)
- Test: [test_tutor_verify_ai_cooldown_and_permissions.py](file:///workspace/core/tests/test_tutor_verify_ai_cooldown_and_permissions.py) (only if needed)

- [ ] **Step 1: Mirror the student implementation**

Copy the same 2-step pipeline to `api_tutor_verify_with_ai`:
- Step 1: recognition-only (vision) using `photo_analysis_model`.
- Step 2: grading (text) using `solution_check_model` fallback to `photo_analysis_model`.
- Same fallback if no reference solution.

- [ ] **Step 2: Add/adjust tests if any tutor AI verify test asserts number of OpenRouter calls**

If existing tests patch `requests.post` once, update with `side_effect` of two responses as in Task 1.

- [ ] **Step 3: Run tests**

```bash
pytest -q
```

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/tests
git commit -m "feat: tutor AI verify uses 2-step solution grading"
```

---

## Task 3: Update remaining OpenRouter verify tests (1-step fallback + 2-image path)

**Files:**
- Modify: [test_submission_verify_openrouter.py](file:///workspace/core/tests/test_submission_verify_openrouter.py)
- Modify: [test_submission_verify_openrouter_two_images.py](file:///workspace/core/tests/test_submission_verify_openrouter_two_images.py)

- [ ] **Step 1: Update baseline verify test to mock 2 calls when solution exists**

Use `post.side_effect = [resp1, resp2]`.

- [ ] **Step 2: Add/adjust a test for fallback to single-step when solution is missing**

Create a TaskVariant with empty solution:

```python
TaskVariant.objects.create(task=self.task, theme="classic", content="<p>Q</p>", solution="")
```

Mock only 1 OpenRouter response (the old single-step grading JSON), and assert that `requests.post` called once.

- [ ] **Step 3: Update two-images test**

Keep step 1 request including both `image_url` items, but step 2 must be text-only.
Assert that:
- first call payload contains 2 images,
- second call payload contains no `image_url` content blocks.

- [ ] **Step 4: Run tests**

```bash
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add core/tests/test_submission_verify_openrouter.py core/tests/test_submission_verify_openrouter_two_images.py
git commit -m "test: update OpenRouter verify tests for 2-step flow"
```

---

## Self-Review Checklist

- [ ] API response fields unchanged for frontend: `primary_score`, `feedback`, `feedback_html`, `recognized_solution`, `mistakes`, `verdict`, `score_breakdown`, `solution_html`, `model`, `cooldown_seconds`.
- [ ] Step-2 uses `solution_check_model` when configured; falls back to `photo_analysis_model`.
- [ ] No step-2 call is made when `solution_html` is empty.
- [ ] Recognition gate (photo_valid / confidence) still forces score=0 and prevents “grading hallucinations”.
- [ ] Tests cover: 2-step success, 1-step fallback, 2-image payload.

