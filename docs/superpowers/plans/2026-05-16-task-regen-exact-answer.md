# Task Regeneration Exact Answer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** При регенерации задачи через OpenRouter сохранять `correct_answer` как точное целое/конечную десятичную дробь без округления, используя `exact_fraction=a/b` из `notes`.

**Architecture:** OpenRouter всегда запрашивается с требованием `exact_fraction=a/b` в `notes`. Сервер парсит дробь, валидирует конечность десятичной записи (после сокращения знаменатель содержит только множители 2 и 5), и сам формирует десятичную строку без округления для `Task.correct_answer`.

**Tech Stack:** Django, Python, Django TestCase

---

## File Structure

**Create**
- `core/answer_format.py` — парсинг `exact_fraction` и конвертация в точную десятичную строку без округления.

**Modify**
- `core/openrouter_client.py` — дописывает технические требования к prompt (чтобы даже при кастомном шаблоне был `exact_fraction`).
- `core/views.py` — `admin_task_regen_preview` и `admin_task_regen_apply` используют нормализованный `correct_answer`, а при ошибке отдают `400`/preview error.

**Tests**
- `core/tests/test_answer_format_exact_fraction.py` — unit тесты конвертации `a/b` → decimal.
- `core/tests/test_admin_task_regen_exact_answer.py` — тесты preview/apply с мокнутым OpenRouter.

---

### Task 1: Unit tests for exact_fraction conversion

**Files:**
- Create: `core/tests/test_answer_format_exact_fraction.py`

- [ ] **Step 1: Write failing tests**

```python
from django.test import TestCase

from core.answer_format import exact_fraction_to_decimal_str


class ExactFractionToDecimalStrTests(TestCase):
    def test_terminating_decimal(self):
        self.assertEqual(exact_fraction_to_decimal_str("7/40"), "0.175")

    def test_reduces_fraction(self):
        self.assertEqual(exact_fraction_to_decimal_str("10/4"), "2.5")

    def test_integer(self):
        self.assertEqual(exact_fraction_to_decimal_str("123/1"), "123")

    def test_negative(self):
        self.assertEqual(exact_fraction_to_decimal_str("-7/40"), "-0.175")

    def test_non_terminating_rejected(self):
        with self.assertRaises(ValueError):
            exact_fraction_to_decimal_str("1/3")
```

- [ ] **Step 2: Run to verify it fails**

Run:

```bash
python manage.py test core.tests.test_answer_format_exact_fraction -v 2
```

Expected: FAIL (`core.answer_format` not found).

---

### Task 2: Implement `core/answer_format.py`

**Files:**
- Create: `core/answer_format.py`
- Test: `core/tests/test_answer_format_exact_fraction.py`

- [ ] **Step 1: Implement minimal conversion logic**

Create `core/answer_format.py`:

```python
import re
from math import gcd


_EXACT_FRACTION_RE = re.compile(r"^\s*([+-]?\d+)\s*/\s*([+-]?\d+)\s*$")


def _strip_trailing_zeros_decimal(s: str) -> str:
    if "." not in s:
        return s
    s = s.rstrip("0").rstrip(".")
    return s or "0"


def exact_fraction_to_decimal_str(frac: str) -> str:
    m = _EXACT_FRACTION_RE.match(frac or "")
    if not m:
        raise ValueError("Invalid exact_fraction format")

    a = int(m.group(1))
    b = int(m.group(2))
    if b == 0:
        raise ValueError("Division by zero")
    if b < 0:
        a = -a
        b = -b

    g = gcd(abs(a), b)
    a //= g
    b //= g

    if b == 1:
        return str(a)

    bb = b
    while bb % 2 == 0:
        bb //= 2
    while bb % 5 == 0:
        bb //= 5
    if bb != 1:
        raise ValueError("Non-terminating decimal")

    k2 = 0
    bb2 = b
    while bb2 % 2 == 0:
        bb2 //= 2
        k2 += 1
    k5 = 0
    bb5 = b
    while bb5 % 5 == 0:
        bb5 //= 5
        k5 += 1

    k = max(k2, k5)
    mul = (2 ** (k - k2)) * (5 ** (k - k5))
    num = a * mul
    den = b * mul  # == 10**k

    sign = "-" if num < 0 else ""
    num_abs = abs(num)

    int_part = num_abs // den
    frac_part = num_abs % den

    frac_str = str(frac_part).rjust(k, "0")
    out = f"{sign}{int_part}.{frac_str}"
    return _strip_trailing_zeros_decimal(out)
```

- [ ] **Step 2: Run tests**

Run:

```bash
python manage.py test core.tests.test_answer_format_exact_fraction -v 2
```

Expected: PASS

---

### Task 3: Parse `exact_fraction` from notes

**Files:**
- Modify: `core/answer_format.py`

- [ ] **Step 1: Add parser**

Append to `core/answer_format.py`:

```python
_NOTES_EXACT_RE = re.compile(r"(?:^|\\s)exact_fraction\\s*=\\s*([+-]?\\d+\\s*/\\s*[+-]?\\d+)(?:\\s|$)")


def extract_exact_fraction(notes: str) -> str:
    m = _NOTES_EXACT_RE.search(notes or "")
    if not m:
        raise ValueError("exact_fraction not found in notes")
    return m.group(1)
```

- [ ] **Step 2: Add tests**

Update `core/tests/test_answer_format_exact_fraction.py`:

```python
from core.answer_format import extract_exact_fraction

def test_extract_exact_fraction(self):
    self.assertEqual(extract_exact_fraction("foo exact_fraction=7/40 bar"), "7/40")
```

- [ ] **Step 3: Run tests**

Run:

```bash
python manage.py test core.tests.test_answer_format_exact_fraction -v 2
```

Expected: PASS

---

### Task 4: Enforce exact_fraction requirement in regen prompt

**Files:**
- Modify: `core/openrouter_client.py`

- [ ] **Step 1: Add technical suffix to prompt**

In `generate_task_regeneration()`, after `prompt` is set, append:

```python
technical_suffix = (
    "\\n\\n"
    "TECHNICAL REQUIREMENTS:\\n"
    "1) Return ONLY valid JSON. No markdown.\\n"
    "2) In notes, include: exact_fraction=a/b where a and b are integers, b>0.\\n"
    "3) correct_answer must be an integer or a terminating decimal WITHOUT rounding/approximation.\\n"
    "4) If the answer would be non-terminating (periodic) or irrational, change the numbers in the task.\\n"
)
prompt = f\"{prompt}{technical_suffix}\"
```

- [ ] **Step 2: Basic compile check**

Run:

```bash
python -m py_compile core/openrouter_client.py
```

Expected: exit code 0

---

### Task 5: Normalize regen result in preview/apply

**Files:**
- Modify: `core/views.py` (`admin_task_regen_preview`, `admin_task_regen_apply`)
- Modify/Create: `core/answer_format.py`
- Test: `core/tests/test_admin_task_regen_exact_answer.py`

- [ ] **Step 1: Write failing view test with mocking**

Create `core/tests/test_admin_task_regen_exact_answer.py`:

```python
import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.models import Subject, Topic, Task, TaskType, ExamFormat, User


class AdminTaskRegenExactAnswerTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pw", role="admin")
        subject = Subject.objects.create(name="Математика")
        exam = ExamFormat.objects.create(subject=subject, name="ЕГЭ", year=2026, is_active=True)
        task_type = TaskType.objects.create(exam_format=exam, number=1, name="Тип 1", max_points=1)
        topic = Topic.objects.create(subject=subject, name="Тема")
        self.task = Task.objects.create(topic=topic, task_type=task_type, correct_answer="0")

    @patch("core.views.generate_task_regeneration")
    def test_preview_returns_normalized_correct_answer(self, gen):
        gen.return_value = {
            "content_html": "<p>x</p>",
            "solution_html": "<p>y</p>",
            "correct_answer": "0.2917",
            "notes": "exact_fraction=7/40",
        }

        self.client.force_login(self.admin)
        url = reverse("admin_task_regen_preview", args=[self.task.id])
        res = self.client.post(url, data=json.dumps({"mode": "full", "model": "m"}), content_type="application/json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["preview"]["correct_answer"], "0.175")

    @patch("core.views.generate_task_regeneration")
    def test_apply_saves_normalized_correct_answer(self, gen):
        gen.return_value = {
            "content_html": "<p>x</p>",
            "solution_html": "<p>y</p>",
            "correct_answer": "0.2917",
            "notes": "exact_fraction=7/40",
        }

        self.client.force_login(self.admin)
        url = reverse("admin_task_regen_apply", args=[self.task.id])
        res = self.client.post(url, data=json.dumps({"mode": "full", "model": "m"}), content_type="application/json")
        self.assertEqual(res.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.correct_answer, "0.175")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python manage.py test core.tests.test_admin_task_regen_exact_answer -v 2
```

Expected: FAIL (пока нет нормализации и patch path может потребовать подстройки).

- [ ] **Step 3: Implement normalization helper**

In `core/answer_format.py` add:

```python
def normalize_regen_correct_answer(*, correct_answer: str, notes: str) -> str:
    frac = extract_exact_fraction(notes)
    return exact_fraction_to_decimal_str(frac)
```

- [ ] **Step 4: Wire into views**

In `core/views.py`, inside both `admin_task_regen_preview` and `admin_task_regen_apply`, after `result = generate_task_regeneration(...)`:

```python
from .answer_format import normalize_regen_correct_answer

try:
    normalized_answer = normalize_regen_correct_answer(
        correct_answer=result.get("correct_answer") or "",
        notes=result.get("notes") or "",
    )
except Exception as e:
    return JsonResponse({"error": str(e)}, status=400)

result["correct_answer"] = normalized_answer
```

Ensure preview uses `result["correct_answer"]`.

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
python manage.py test core.tests.test_answer_format_exact_fraction core.tests.test_admin_task_regen_exact_answer -v 2
```

Expected: PASS

---

### Task 6: Final checks and commit

**Files:**
- Modify/Create: all above

- [ ] **Step 1: Lint/compile checks**

Run:

```bash
python -m py_compile core/answer_format.py core/openrouter_client.py
```

- [ ] **Step 2: Commit**

```bash
git add core/answer_format.py core/openrouter_client.py core/views.py core/tests/test_answer_format_exact_fraction.py core/tests/test_admin_task_regen_exact_answer.py
git commit -m "fix(task-regen): enforce exact_fraction and avoid rounded answers"
```

