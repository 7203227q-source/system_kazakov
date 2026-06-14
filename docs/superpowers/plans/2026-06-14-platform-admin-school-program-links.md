# Platform Admin School Program Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `Школьная программа` section to `platform-admin` with a dedicated page of quick links and onboarding steps for the school-program models.

**Architecture:** Reuse the existing `platform-admin` server-rendered pattern: one new route, one admin-only view, one new template, and sidebar-link updates in the current admin templates. The new page acts as a navigation hub and intentionally links to the existing Django admin model pages instead of duplicating CRUD forms.

**Tech Stack:** Django 6, existing `core.views` / `core.urls`, server-rendered HTML templates with Tailwind, Django TestCase.

---

## File Structure

**Create**
- `core/templates/core/admin_school_program.html` — new platform-admin page for school-program navigation.
- `core/tests/test_admin_school_program.py` — admin-only access, rendered cards, quick links, and sidebar presence.

**Modify**
- `core/views.py` — add `admin_school_program` view and page context.
- `core/urls.py` — register `/platform-admin/school-program/`.
- `core/templates/core/admin_dashboard.html` — add sidebar item for the new section.
- `core/templates/core/admin_exam_structure.html` — add sidebar item for the new section.
- `core/templates/core/admin_reshuege_import.html` — add sidebar item for the new section.
- `core/templates/core/admin_system.html` — add sidebar item for the new section.
- `core/templates/core/admin_openrouter_balance.html` — add sidebar item for the new section.
- `core/templates/core/admin_task_error_reports.html` — add sidebar item for the new section.
- `core/templates/core/admin_task_error_report_detail.html` — add sidebar item for the new section.

---

### Task 1: Add Admin School Program Page

**Files:**
- Create: `core/tests/test_admin_school_program.py`
- Create: `core/templates/core/admin_school_program.html`
- Modify: `core/views.py`
- Modify: `core/urls.py`

- [ ] **Step 1: Write the failing tests**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import User


class AdminSchoolProgramTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pass", role="admin")
        self.tutor = User.objects.create_user(username="tutor", password="pass", role="tutor")

    def test_requires_admin(self):
        self.client.force_login(self.tutor)
        res = self.client.get(reverse("admin_school_program"))
        self.assertIn(res.status_code, (302, 403))

    def test_admin_can_open_school_program_page(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse("admin_school_program"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Школьная программа")
        self.assertContains(res, "Быстрый старт")
        self.assertContains(res, "/admin/core/learningtrack/")
        self.assertContains(res, "/admin/core/curriculumtopic/")
        self.assertContains(res, "/admin/core/schooltaskmeta/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_admin_school_program -v 2`
Expected: FAIL with `NoReverseMatch` because `admin_school_program` route does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add route in `core/urls.py`:

```python
path("platform-admin/school-program/", views.admin_school_program, name="admin_school_program"),
```

Add view in `core/views.py`:

```python
@login_required
def admin_school_program(request):
    if request.user.role != "admin":
        return redirect("login")

    sections = [
        {
            "title": "Курсы",
            "subtitle": "LearningTrack",
            "description": "Курсы школьного контура, например «Математика, 7 класс».",
            "list_url": "/admin/core/learningtrack/",
            "add_url": "/admin/core/learningtrack/add/",
        },
        {
            "title": "Разделы",
            "subtitle": "CurriculumUnit",
            "description": "Крупные разделы программы внутри курса.",
            "list_url": "/admin/core/curriculumunit/",
            "add_url": "/admin/core/curriculumunit/add/",
        },
        {
            "title": "Темы",
            "subtitle": "CurriculumTopic",
            "description": "Конкретные темы, которые проходят ученики.",
            "list_url": "/admin/core/curriculumtopic/",
            "add_url": "/admin/core/curriculumtopic/add/",
        },
        {
            "title": "Типы заданий",
            "subtitle": "LearningTaskType",
            "description": "Учебные типы задач для школьного курса.",
            "list_url": "/admin/core/learningtasktype/",
            "add_url": "/admin/core/learningtasktype/add/",
        },
        {
            "title": "Связка заданий",
            "subtitle": "SchoolTaskMeta",
            "description": "Привязка задач к теме, курсу и учебному типу.",
            "list_url": "/admin/core/schooltaskmeta/",
            "add_url": "/admin/core/schooltaskmeta/add/",
        },
        {
            "title": "Индивидуальные планы",
            "subtitle": "StudentLearningPlan",
            "description": "Персональные программы учеников.",
            "list_url": "/admin/core/studentlearningplan/",
            "add_url": "/admin/core/studentlearningplan/add/",
        },
        {
            "title": "Шаги плана",
            "subtitle": "PlanItem",
            "description": "Отдельные шаги внутри индивидуального плана.",
            "list_url": "/admin/core/planitem/",
            "add_url": "/admin/core/planitem/add/",
        },
    ]
    quick_start_steps = [
        "Открыть курс «Математика, 7 класс»",
        "Создать или проверить разделы",
        "Добавить темы программы",
        "Добавить типы заданий",
        "Привязать задачи через SchoolTaskMeta",
        "Создать индивидуальный план",
    ]
    return render(
        request,
        "core/admin_school_program.html",
        {"sections": sections, "quick_start_steps": quick_start_steps},
    )
```

Create `core/templates/core/admin_school_program.html` reusing the existing platform-admin style with:

```django
<h1>Школьная программа</h1>
<section>Быстрый старт</section>
{% for section in sections %}
  <a href="{{ section.list_url }}">Открыть список</a>
  <a href="{{ section.add_url }}">Добавить</a>
{% endfor %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_admin_school_program -v 2`
Expected: PASS with 2 tests.

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/urls.py core/templates/core/admin_school_program.html core/tests/test_admin_school_program.py
git commit -m "feat: add school program page to platform admin"
```

### Task 2: Add Sidebar Link Across Platform Admin

**Files:**
- Create: `core/tests/test_admin_school_program.py`
- Modify: `core/templates/core/admin_dashboard.html`
- Modify: `core/templates/core/admin_exam_structure.html`
- Modify: `core/templates/core/admin_reshuege_import.html`
- Modify: `core/templates/core/admin_system.html`
- Modify: `core/templates/core/admin_openrouter_balance.html`
- Modify: `core/templates/core/admin_task_error_reports.html`
- Modify: `core/templates/core/admin_task_error_report_detail.html`

- [ ] **Step 1: Write the failing sidebar test**

```python
def test_existing_platform_admin_pages_include_school_program_menu_link(self):
    self.client.force_login(self.admin)
    pages = [
        reverse("admin_dashboard"),
        reverse("admin_exam_structure"),
        reverse("admin_reshuege_import"),
        reverse("admin_system"),
        reverse("admin_openrouter_balance"),
        reverse("admin_task_error_reports"),
    ]
    for url in pages:
        with self.subTest(url=url):
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200)
            self.assertContains(res, reverse("admin_school_program"))
            self.assertContains(res, "Школьная программа")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test core.tests.test_admin_school_program.AdminSchoolProgramTests.test_existing_platform_admin_pages_include_school_program_menu_link -v 2`
Expected: FAIL because the sidebar link is not present in current templates.

- [ ] **Step 3: Write minimal implementation**

Add the same sidebar entry to each platform-admin template:

```django
<a href="{% url 'admin_school_program' %}" class="flex items-center px-4 py-3 text-gray-400 hover:bg-gray-800 hover:text-white rounded-lg transition">
    <i class="fas fa-book-open w-6 text-gray-400"></i> Школьная программа
</a>
```

On `admin_school_program.html`, render it as active:

```django
<a href="{% url 'admin_school_program' %}" class="flex items-center px-4 py-3 bg-gray-800 text-white rounded-lg">
    <i class="fas fa-book-open w-6 text-indigo-400"></i> Школьная программа
</a>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test core.tests.test_admin_school_program.AdminSchoolProgramTests.test_existing_platform_admin_pages_include_school_program_menu_link -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/templates/core/admin_dashboard.html core/templates/core/admin_exam_structure.html core/templates/core/admin_reshuege_import.html core/templates/core/admin_system.html core/templates/core/admin_openrouter_balance.html core/templates/core/admin_task_error_reports.html core/templates/core/admin_task_error_report_detail.html core/tests/test_admin_school_program.py
git commit -m "feat: add school program menu to platform admin"
```

### Task 3: Run Focused Regression Suite

**Files:**
- Test: `core/tests/test_admin_school_program.py`
- Test: `core/tests/test_admin_task_error_reports.py`

- [ ] **Step 1: Run the new school-program admin tests**

Run: `python manage.py test core.tests.test_admin_school_program -v 2`
Expected: PASS.

- [ ] **Step 2: Run nearby platform-admin regression**

Run: `python manage.py test core.tests.test_admin_task_error_reports -v 2`
Expected: PASS to confirm the new menu item does not break nearby admin pages.

- [ ] **Step 3: Run lint on touched files**

Run: `ruff check core/views.py core/urls.py core/templates/core/admin_dashboard.html core/templates/core/admin_exam_structure.html core/templates/core/admin_reshuege_import.html core/templates/core/admin_system.html core/templates/core/admin_openrouter_balance.html core/templates/core/admin_task_error_reports.html core/templates/core/admin_task_error_report_detail.html core/templates/core/admin_school_program.html core/tests/test_admin_school_program.py`
Expected: Template files are ignored by `ruff`; Python files and tests pass. If `core/views.py` still shows legacy lint debt unrelated to this task, record it separately.

- [ ] **Step 4: Manual smoke checklist**

Open in browser after deploy:
- `/platform-admin/`
- verify menu item `Школьная программа`
- open `/platform-admin/school-program/`
- verify all 7 cards render
- verify `Открыть список` and `Добавить` buttons point to the expected `/admin/core/...` URLs

Expected: all checks pass.

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/urls.py core/templates/core/admin_school_program.html core/templates/core/admin_dashboard.html core/templates/core/admin_exam_structure.html core/templates/core/admin_reshuege_import.html core/templates/core/admin_system.html core/templates/core/admin_openrouter_balance.html core/templates/core/admin_task_error_reports.html core/templates/core/admin_task_error_report_detail.html core/tests/test_admin_school_program.py docs/superpowers/plans/2026-06-14-platform-admin-school-program-links.md
git commit -m "test: verify platform admin school program links"
```

## Self-Review Notes

- Spec coverage:
  - new route and section page: Task 1
  - quick links and quick-start block: Task 1
  - sidebar entry in platform-admin: Task 2
  - nearby platform-admin regression: Task 3
- No placeholders remain.
- Naming consistency is locked to:
  - `admin_school_program`
  - `admin_school_program.html`
  - `Школьная программа`
