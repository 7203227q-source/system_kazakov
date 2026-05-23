# Moscow Time Student Greeting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать приветствие на панели ученика динамическим по московскому времени (ночь/утро/день/вечер).

**Architecture:** Серверная функция `get_time_greeting()` определяет приветствие по `timezone.now()` в `Europe/Moscow`. Шаблон использует Django template tag `{% time_greeting %}` и не зависит от времени браузера.

**Tech Stack:** Django 6, Django templates, zoneinfo, django.utils.timezone, unittest.mock, pytest (как раннер тестов) / Django TestCase.

---

## File Map

- Create: `/workspace/core/greetings.py` — чистая функция выбора приветствия на основании времени в `Europe/Moscow`.
- Create: `/workspace/core/templatetags/time_greeting.py` — template tag `{% time_greeting %}` для использования в шаблонах.
- Modify: `/workspace/core/templates/core/student_dashboard.html` — заменить «Доброе утро» на `{% time_greeting %}`.
- Create: `/workspace/core/tests/test_time_greeting.py` — тесты границ интервалов и smoke-тест template tag’а.

---

### Task 1: Add Greeting Tests (TDD)

**Files:**
- Create: `/workspace/core/tests/test_time_greeting.py`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.template import Context, Template
from django.test import TestCase


class TimeGreetingTests(TestCase):
    def test_night_end_boundary(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 4, 59, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Доброй ночи")

    def test_morning_start_boundary(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 5, 0, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Доброе утро")

    def test_morning_end_boundary(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 11, 59, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Доброе утро")

    def test_day_start_boundary(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 12, 0, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Добрый день")

    def test_day_end_boundary(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 17, 59, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Добрый день")

    def test_evening_start_boundary(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 18, 0, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Добрый вечер")

    def test_midnight_is_night(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 14, 0, 0, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Доброй ночи")

    def test_template_tag_renders(self):
        tz = ZoneInfo("Europe/Moscow")
        mocked_now = datetime(2026, 5, 13, 12, 0, tzinfo=tz)

        with patch("core.greetings.timezone.now", return_value=mocked_now):
            tpl = Template("{% load time_greeting %}{% time_greeting %}")
            self.assertEqual(tpl.render(Context({})), "Добрый день")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q core/tests/test_time_greeting.py -vv
```

Expected: FAIL (например, `ModuleNotFoundError: No module named 'core.greetings'`).

- [ ] **Step 3: Commit (optional)**

```bash
git add core/tests/test_time_greeting.py
git commit -m "test: add time-based greeting tests"
```

---

### Task 2: Implement `get_time_greeting()`

**Files:**
- Create: `/workspace/core/greetings.py`
- Test: `/workspace/core/tests/test_time_greeting.py`

- [ ] **Step 1: Add minimal implementation**

```python
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone


def get_time_greeting(now: datetime | None = None, tz_name: str = "Europe/Moscow") -> str:
    tz = ZoneInfo(tz_name)
    now_dt = now or timezone.now()

    if timezone.is_naive(now_dt):
        now_dt = timezone.make_aware(now_dt, tz)

    local_now = timezone.localtime(now_dt, tz)
    hour = local_now.hour

    if 0 <= hour <= 4:
        return "Доброй ночи"
    if 5 <= hour <= 11:
        return "Доброе утро"
    if 12 <= hour <= 17:
        return "Добрый день"
    return "Добрый вечер"
```

- [ ] **Step 2: Run tests to verify they pass**

Run:

```bash
pytest -q core/tests/test_time_greeting.py -vv
```

Expected: PASS.

- [ ] **Step 3: Commit (optional)**

```bash
git add core/greetings.py
git commit -m "feat: add moscow-time greeting selector"
```

---

### Task 3: Add Template Tag `{% time_greeting %}`

**Files:**
- Create: `/workspace/core/templatetags/time_greeting.py`
- Test: `/workspace/core/tests/test_time_greeting.py`

- [ ] **Step 1: Create template tag module**

```python
from django import template

from core.greetings import get_time_greeting

register = template.Library()


@register.simple_tag
def time_greeting():
    return get_time_greeting()
```

- [ ] **Step 2: Re-run tests**

Run:

```bash
pytest -q core/tests/test_time_greeting.py -vv
```

Expected: PASS.

- [ ] **Step 3: Commit (optional)**

```bash
git add core/templatetags/time_greeting.py
git commit -m "feat: add time_greeting template tag"
```

---

### Task 4: Use Greeting in Student Dashboard Template

**Files:**
- Modify: `/workspace/core/templates/core/student_dashboard.html`

- [ ] **Step 1: Load the tag library**

Add the first line:

```django
{% load time_greeting %}
```

So the file begins like:

```django
{% load time_greeting %}
<!DOCTYPE html>
<html lang="ru">
```

- [ ] **Step 2: Replace hardcoded greeting**

Replace:

```django
<h1 class="text-2xl font-bold text-gray-800 mb-6">Доброе утро, {{ user.first_name|default:user.username }}! 👋</h1>
```

With:

```django
<h1 class="text-2xl font-bold text-gray-800 mb-6">{% time_greeting %}, {{ user.first_name|default:user.username }}! 👋</h1>
```

- [ ] **Step 3: Run targeted tests**

Run:

```bash
pytest -q core/tests/test_time_greeting.py -vv
```

Expected: PASS.

- [ ] **Step 4: Run full test suite smoke (optional)**

Run:

```bash
pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit (optional)**

```bash
git add core/templates/core/student_dashboard.html
git commit -m "feat: use moscow-time greeting on student dashboard"
```

---

## Plan Self-Review

- Spec coverage: реализует server-side вычисление приветствия по Москве и подключение в `student_dashboard.html`; тестирует границы интервалов и wiring template tag’а.
- Placeholder scan: отсутствуют TODO/TBD; все шаги содержат конкретные пути, код и команды.
- Consistency: `Europe/Moscow` единообразно используется в тестах и дефолтном `tz_name`.

