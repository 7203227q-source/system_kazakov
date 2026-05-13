# Moscow time + “сегодня/вчера” for Chat & Comments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести отображение времени в чате и комментариях к заданиям на московское время и единый формат: `сегодня HH:MM`, `вчера HH:MM`, иначе `DD.MM HH:MM` (и `DD.MM.YYYY HH:MM` если год не текущий).

**Architecture:** Django остаётся с `USE_TZ=True` (UTC в БД), но `TIME_ZONE` меняется на `Europe/Moscow`. Вся логика UI-форматирования времени централизуется в одном python helper `format_ui_datetime()`, который используется как в template filter `ui_datetime`, так и в chat API (возвращаем `created_at_label`).

**Tech Stack:** Django 6.x, templates, custom template tags, `zoneinfo`.

---

## Files to Touch

- Modify: `/workspace/examprep/settings.py`
- Create: `/workspace/core/utils/datetime_ui.py`
- Create: `/workspace/core/templatetags/__init__.py`
- Create: `/workspace/core/templatetags/ui_datetime.py`
- Modify: `/workspace/core/views_chat.py`
- Modify: `/workspace/core/templates/core/chat.html`
- Modify: `/workspace/core/templates/core/student_solve_assignment.html`
- Create: `/workspace/core/tests/test_ui_datetime_format.py`
- Create: `/workspace/core/tests/test_chat_api_datetime_label.py`

---

### Task 1: RED — тесты форматтера `сегодня/вчера/дата`

**Files:**
- Create: `/workspace/core/tests/test_ui_datetime_format.py`

- [ ] **Step 1: Write failing tests**

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone


class UIDatetimeFormatTests(TestCase):
    def test_today(self):
        from core.utils.datetime_ui import format_ui_datetime
        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 10, 0, tzinfo=tz)
        dt = datetime(2026, 5, 13, 9, 5, tzinfo=tz)
        self.assertEqual(format_ui_datetime(dt, now=now), "сегодня 09:05")

    def test_yesterday(self):
        from core.utils.datetime_ui import format_ui_datetime
        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 10, 0, tzinfo=tz)
        dt = datetime(2026, 5, 12, 21, 10, tzinfo=tz)
        self.assertEqual(format_ui_datetime(dt, now=now), "вчера 21:10")

    def test_other_date_current_year(self):
        from core.utils.datetime_ui import format_ui_datetime
        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 10, 0, tzinfo=tz)
        dt = datetime(2026, 4, 2, 8, 0, tzinfo=tz)
        self.assertEqual(format_ui_datetime(dt, now=now), "02.04 08:00")

    def test_other_date_other_year(self):
        from core.utils.datetime_ui import format_ui_datetime
        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 10, 0, tzinfo=tz)
        dt = datetime(2025, 12, 31, 23, 59, tzinfo=tz)
        self.assertEqual(format_ui_datetime(dt, now=now), "31.12.2025 23:59")
```

- [ ] **Step 2: Run tests (expect FAIL)**

```bash
python manage.py test core.tests.test_ui_datetime_format -v 1
```

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_ui_datetime_format.py
git commit -m "test: ui datetime formatting today/yesterday"
```

---

### Task 2: GREEN — реализовать helper и template filter

**Files:**
- Create: `/workspace/core/utils/datetime_ui.py`
- Create: `/workspace/core/templatetags/ui_datetime.py`

- [ ] **Step 1: Implement helper**

`core/utils/datetime_ui.py`:
```python
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone


def format_ui_datetime(dt: datetime | None, now: datetime | None = None, tz_name: str = "Europe/Moscow") -> str:
    if not dt:
        return ""
    tz = ZoneInfo(tz_name)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, tz)
    local_dt = timezone.localtime(dt, tz)

    now_dt = now or timezone.now()
    if timezone.is_naive(now_dt):
        now_dt = timezone.make_aware(now_dt, tz)
    local_now = timezone.localtime(now_dt, tz)

    if local_dt.date() == local_now.date():
        return f"сегодня {local_dt:%H:%M}"
    if local_dt.date() == (local_now.date() - timedelta(days=1)):
        return f"вчера {local_dt:%H:%M}"

    if local_dt.year != local_now.year:
        return f"{local_dt:%d.%m.%Y %H:%M}"
    return f"{local_dt:%d.%m %H:%M}"
```

- [ ] **Step 2: Implement template filter**

`core/templatetags/ui_datetime.py`:
```python
from django import template
from core.utils.datetime_ui import format_ui_datetime

register = template.Library()

@register.filter
def ui_datetime(value):
    return format_ui_datetime(value)
```

- [ ] **Step 3: Run formatter tests**

```bash
python manage.py test core.tests.test_ui_datetime_format -v 1
```

- [ ] **Step 4: Commit**

```bash
git add core/utils/datetime_ui.py core/templatetags/ui_datetime.py core/templatetags/__init__.py
git commit -m "feat: ui datetime formatter and template filter"
```

---

### Task 3: GREEN — включить TIME_ZONE Europe/Moscow

**Files:**
- Modify: `/workspace/examprep/settings.py`

- [ ] **Step 1: Update TIME_ZONE**

```python
TIME_ZONE = "Europe/Moscow"
USE_TZ = True
```

- [ ] **Step 2: Run a small smoke suite**

```bash
python manage.py test core.tests.test_ui_datetime_format -v 1
```

- [ ] **Step 3: Commit**

```bash
git add examprep/settings.py
git commit -m "chore: set default timezone to Europe/Moscow"
```

---

### Task 4: GREEN — комментарии: заменить форматирование на `ui_datetime`

**Files:**
- Modify: `/workspace/core/templates/core/student_solve_assignment.html`

- [ ] **Step 1: Replace `|date:"d.m H:i"`**
  - на `|ui_datetime`
  - добавить `{% load ui_datetime %}` (или общий load, если уже есть)

- [ ] **Step 2: Run existing comment tests**

```bash
python manage.py test core.tests.test_submission_comments -v 1
```

- [ ] **Step 3: Commit**

```bash
git add core/templates/core/student_solve_assignment.html
git commit -m "feat: show comment timestamps as today/yesterday"
```

---

### Task 5: RED/GREEN — chat API отдаёт `created_at_label`, фронт использует её

**Files:**
- Create: `/workspace/core/tests/test_chat_api_datetime_label.py`
- Modify: `/workspace/core/views_chat.py`
- Modify: `/workspace/core/templates/core/chat.html`

- [ ] **Step 1: Add failing API test**

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse

from core.models import Message, TutorStudentLink, User


class ChatApiDatetimeLabelTests(TestCase):
    def test_api_returns_created_at_label(self):
        tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        student = User.objects.create_user(username="s", password="pass", role="student")
        TutorStudentLink.objects.create(tutor=tutor, student=student)
        m = Message.objects.create(sender=student, receiver=tutor, content="hi")
        Message.objects.filter(id=m.id).update(created_at=datetime(2026, 5, 13, 6, 5, tzinfo=ZoneInfo("UTC")))

        self.client.login(username="t", password="pass")
        res = self.client.get(reverse("api_get_messages", args=[student.id]) + "?after=0")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertTrue(payload["messages"])
        self.assertIn("created_at_label", payload["messages"][0])
        self.assertTrue(payload["messages"][0]["created_at_label"])
```

- [ ] **Step 2: Run test (expect FAIL)**

```bash
python manage.py test core.tests.test_chat_api_datetime_label -v 1
```

- [ ] **Step 3: Update `api_get_messages`**
  - добавить `created_at_label: format_ui_datetime(msg.created_at)`
  - можно оставить старое `created_at` как `HH:MM` для обратной совместимости

- [ ] **Step 4: Update `chat.html`**
  - `appendMessageToDOM`: использовать `msg.created_at_label || msg.created_at`
  - sidebar last message time: `{{ d.last_message.created_at|ui_datetime }}`
  - добавить `{% load ui_datetime %}`

- [ ] **Step 5: Run tests**

```bash
python manage.py test core.tests.test_chat_api_datetime_label -v 1
python manage.py test core.tests.test_chat_input_visible core.tests.test_chat_dialog_sidebar_order -v 1
```

- [ ] **Step 6: Commit**

```bash
git add core/views_chat.py core/templates/core/chat.html core/tests/test_chat_api_datetime_label.py
git commit -m "feat: chat shows moscow time with today/yesterday labels"
```

---

### Task 6: Regression suite + push

- [ ] **Step 1: Run full test suite**

```bash
python manage.py test core.tests -v 1
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

