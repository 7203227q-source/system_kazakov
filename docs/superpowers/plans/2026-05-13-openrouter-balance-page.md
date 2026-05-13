# OpenRouter Balance Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в админке страницу “OpenRouter: баланс”, показывающую данные `/key` всегда и (при наличии `OPENROUTER_MANAGEMENT_KEY`) — `/credits` и `/activity` с расходом по моделям.

**Architecture:** Новый admin-view собирает данные из OpenRouter (requests.get) и рендерит отдельный шаблон. При отсутствии management key — показываем подсказку. Ошибки сети не ломают страницу.

**Tech Stack:** Django views/templates/urls, requests, Django TestCase.

---

## Files (map)

**Create**
- `/workspace/core/templates/core/admin_openrouter_balance.html`
- `/workspace/core/tests/test_admin_openrouter_balance.py`

**Modify**
- `/workspace/core/views.py` — новый view `admin_openrouter_balance`
- `/workspace/core/urls.py` — новый route
- `/workspace/core/templates/core/admin_system.html` — ссылка в левом меню (или отдельный пункт)

---

### Task 1: RED — тесты доступа и fallback без management key

**Files:**
- Create: `/workspace/core/tests/test_admin_openrouter_balance.py`

- [ ] **Step 1: Write failing tests**

```python
import os
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.models import User


class AdminOpenRouterBalanceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="a", password="pass", role="admin")
        self.student = User.objects.create_user(username="s", password="pass", role="student")

    def test_requires_admin(self):
        self.client.login(username="s", password="pass")
        res = self.client.get(reverse("admin_openrouter_balance"))
        self.assertIn(res.status_code, (302, 403))

    def test_renders_without_management_key(self):
        os.environ["OPENROUTER_API_KEY"] = "test"
        if "OPENROUTER_MANAGEMENT_KEY" in os.environ:
            del os.environ["OPENROUTER_MANAGEMENT_KEY"]

        with patch("core.views.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = {"data": {"label": "k", "limit": None, "limit_remaining": None, "usage": 1, "usage_daily": 1, "usage_weekly": 1, "usage_monthly": 1}}

            self.client.force_login(self.admin)
            res = self.client.get(reverse("admin_openrouter_balance"))

        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "OPENROUTER_MANAGEMENT_KEY")
```

- [ ] **Step 2: Run to verify fails**

```bash
python manage.py test core.tests.test_admin_openrouter_balance -v 1
```

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_admin_openrouter_balance.py
git commit -m "test: admin openrouter balance page"
```

---

### Task 2: GREEN — view + url + template (без management key)

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/urls.py`
- Create: `/workspace/core/templates/core/admin_openrouter_balance.html`

- [ ] **Step 1: Implement view**
Создать `admin_openrouter_balance`:
- проверка `request.user.role == 'admin'`
- читать `OPENROUTER_API_KEY` из ENV
- если ключа нет: status=missing
- если есть: `GET https://openrouter.ai/api/v1/key` с Bearer
- try/except вокруг requests/json

- [ ] **Step 2: Add route**
`path('admin/openrouter/balance/', views.admin_openrouter_balance, name='admin_openrouter_balance')`

- [ ] **Step 3: Create template**
Показать:
- статус ключа
- таблицу с limit/remaining + usage daily/weekly/monthly
- блок “Для расходов по моделям нужен OPENROUTER_MANAGEMENT_KEY”

- [ ] **Step 4: Run tests**

```bash
python manage.py test core.tests.test_admin_openrouter_balance -v 1
```

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/urls.py core/templates/core/admin_openrouter_balance.html
git commit -m "feat: admin openrouter balance page (key info)"
```

---

### Task 3: GREEN — блоки credits + activity (включаются при наличии management key)

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/admin_openrouter_balance.html`
- Modify: `/workspace/core/tests/test_admin_openrouter_balance.py`

- [ ] **Step 1: Extend test with management key**
Добавить тест, где выставляем `OPENROUTER_MANAGEMENT_KEY="mtest"` и мок `requests.get`:
- `/credits` → `{"data":{"total_credits":100,"total_usage":25}}`
- `/activity` → `{"data":[{"model":"m1","usage":1.5,"requests":2},{"model":"m1","usage":0.5,"requests":1},{"model":"m2","usage":3.0,"requests":4}]}`
Ожидаем, что страница покажет `m2` и `3.0`, `m1` и `2.0`.

- [ ] **Step 2: Implement aggregation**
В view:
- при наличии management key дергаем `/credits` и `/activity`
- агрегируем по `model`: sum(usage), sum(requests)
- сортировка по usage desc

- [ ] **Step 3: Render in template**
Таблица “Расход по моделям (30 дней)”.

- [ ] **Step 4: Run tests**

```bash
python manage.py test core.tests.test_admin_openrouter_balance -v 1
```

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/templates/core/admin_openrouter_balance.html core/tests/test_admin_openrouter_balance.py
git commit -m "feat: show openrouter credits and per-model spend (when configured)"
```

---

### Task 4: Link from admin sidebar + regression + push

**Files:**
- Modify: `/workspace/core/templates/core/admin_system.html`

- [ ] **Step 1: Add link in sidebar**
Добавить пункт меню:
`{% url 'admin_openrouter_balance' %}`.

- [ ] **Step 2: Run full suite**

```bash
python manage.py test core.tests -v 1
```

- [ ] **Step 3: Push**

```bash
git push origin main
```

