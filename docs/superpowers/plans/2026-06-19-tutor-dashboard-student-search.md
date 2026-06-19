# Tutor Dashboard Student Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать кнопку `Добавить ученика` из панели репетитора и сделать рабочим серверный `GET`-поиск учеников по `q` в `tutor_dashboard`.

**Architecture:** Вся логика остается внутри `tutor_dashboard`: queryset учеников репетитора фильтруется по `q`, затем на него навешиваются текущие `prefetch_related/annotate`, а выбор `selected_student` ограничивается только текущим filtered queryset. В шаблоне `tutor_dashboard.html` header search превращается в GET-форму, кнопка удаляется, ссылки в списке учеников сохраняют query state (`q`, `subject_id`, `range`), а при пустом результате показывается empty state.

**Tech Stack:** Django views, Django ORM (`Q`), Django templates, Django TestCase.

---

## Изменяемые файлы (map)

**Modify**
- `/workspace/core/views.py` — добавить `search_query`, фильтрацию queryset учеников и безопасный selection fallback
- `/workspace/core/templates/core/tutor_dashboard.html` — удалить кнопку, превратить input в GET-form, сохранить query state, добавить empty state
- `/workspace/core/tests/test_tutor_selected_student_persists_across_pages.py` — обновить ожидания ссылок с учетом `q`

**Create**
- `/workspace/core/tests/test_tutor_dashboard_student_search.py` — новые tests на поиск, отсутствие кнопки, empty state и selection behavior

---

### Task 1: Написать failing tests на новый поиск и отсутствие кнопки

**Files:**
- Create: `/workspace/core/tests/test_tutor_dashboard_student_search.py`
- Test: `/workspace/core/templates/core/tutor_dashboard.html`
- Test: `/workspace/core/views.py`

- [ ] **Step 1: Write the failing tests**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import User


class TutorDashboardStudentSearchTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="tutor", password="pass", role="tutor")
        self.student_anna = User.objects.create_user(
            username="anna_ivanova",
            password="pass",
            role="student",
            first_name="Анна",
            last_name="Иванова",
            email="anna@example.com",
        )
        self.student_boris = User.objects.create_user(
            username="boris_petrov",
            password="pass",
            role="student",
            first_name="Борис",
            last_name="Петров",
            email="boris@example.com",
        )
        self.tutor.students.add(self.student_anna, self.student_boris)
        self.client.login(username="tutor", password="pass")

    def test_search_filters_students_and_hides_add_button(self):
        res = self.client.get(reverse("tutor_dashboard"), {"q": "Анна"})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Анна")
        self.assertNotContains(res, "Борис")
        self.assertNotContains(res, "Добавить ученика")

    def test_search_preserves_query_state_in_student_links(self):
        res = self.client.get(
            reverse("tutor_dashboard"),
            {"q": "anna", "subject_id": "7", "range": "90"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(
            res,
            f'?student_id={self.student_anna.id}&q=anna&subject_id=7&range=90',
        )

    def test_empty_search_result_renders_empty_state(self):
        res = self.client.get(reverse("tutor_dashboard"), {"q": "zzz"})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Ученики не найдены")

    def test_selected_student_falls_back_to_first_filtered_result(self):
        res = self.client.get(
            reverse("tutor_dashboard"),
            {"student_id": self.student_boris.id, "q": "Анна"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["selected_student"].id, self.student_anna.id)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python manage.py test core.tests.test_tutor_dashboard_student_search -v 1
```

Expected: FAIL because the search input is not wired, the add button still exists, links do not preserve `q`, and there is no empty state.

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_tutor_dashboard_student_search.py
git commit -m "test: cover tutor dashboard student search"
```

---

### Task 2: Реализовать фильтрацию учеников по `q` во view

**Files:**
- Modify: `/workspace/core/views.py`
- Test: `/workspace/core/tests/test_tutor_dashboard_student_search.py`

- [ ] **Step 1: Write the minimal implementation**

В начале построения списка учеников внутри `tutor_dashboard()` добавить:

```python
search_query = (request.GET.get("q") or "").strip()
```

Заменить базовый queryset:

```python
students = (
    request.user.students.all()
    .prefetch_related('subject_profiles', 'subject_profiles__subject')
    .annotate(
        unread_student_questions=Coalesce(Subquery(unresolved_qs, output_field=IntegerField()), 0),
        latest_unread_submission_id=Subquery(latest_unread_submission_qs, output_field=IntegerField()),
        pending_extension_requests=Coalesce(Subquery(pending_extension_qs, output_field=IntegerField()), 0),
        pending_srs_removal_requests=Coalesce(Subquery(pending_srs_removal_qs, output_field=IntegerField()), 0),
    )
)
```

на:

```python
students = request.user.students.all()
if search_query:
    students = students.filter(
        Q(first_name__icontains=search_query)
        | Q(last_name__icontains=search_query)
        | Q(username__icontains=search_query)
        | Q(email__icontains=search_query)
    )
students = (
    students
    .prefetch_related('subject_profiles', 'subject_profiles__subject')
    .annotate(
        unread_student_questions=Coalesce(Subquery(unresolved_qs, output_field=IntegerField()), 0),
        latest_unread_submission_id=Subquery(latest_unread_submission_qs, output_field=IntegerField()),
        pending_extension_requests=Coalesce(Subquery(pending_extension_qs, output_field=IntegerField()), 0),
        pending_srs_removal_requests=Coalesce(Subquery(pending_srs_removal_qs, output_field=IntegerField()), 0),
    )
)
```

- [ ] **Step 2: Restrict selection fallback to filtered queryset**

После разбора `selected_student_id` заменить логику выбора на:

```python
if selected_student_id:
    selected_student = students.filter(id=int(selected_student_id)).first()
if not selected_student:
    selected_student = students.first()
```

И передать в context:

```python
'search_query': search_query,
```

- [ ] **Step 3: Run tests to verify they pass**

Run:
```bash
python manage.py test core.tests.test_tutor_dashboard_student_search -v 1
```

Expected: part of tests may still fail until template is updated, but `selected_student` fallback should be correct in context once the view is done.

- [ ] **Step 4: Commit**

```bash
git add core/views.py
git commit -m "feat: filter tutor students by search query"
```

---

### Task 3: Подключить GET-form, убрать кнопку и сохранить query state в шаблоне

**Files:**
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`
- Test: `/workspace/core/tests/test_tutor_dashboard_student_search.py`

- [ ] **Step 1: Replace the header search block**

Заменить:

```django
<div class="relative hidden sm:block">
    <i class="fas fa-search absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400"></i>
    <input type="text" placeholder="Поиск ученика..." class="pl-10 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent w-48">
</div>
<button class="bg-primary text-white px-3 py-2 md:px-4 md:py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 transition flex items-center">
    <i class="fas fa-plus md:mr-2"></i> <span class="hidden md:inline">Добавить ученика</span>
</button>
```

на:

```django
<form method="get" class="relative hidden sm:block">
    {% if selected_student %}
    <input type="hidden" name="student_id" value="{{ selected_student.id }}">
    {% endif %}
    {% if chart_subject_id %}
    <input type="hidden" name="subject_id" value="{{ chart_subject_id }}">
    {% endif %}
    {% if chart_range %}
    <input type="hidden" name="range" value="{{ chart_range }}">
    {% endif %}
    <i class="fas fa-search absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400"></i>
    <input
        type="text"
        name="q"
        value="{{ search_query|default:'' }}"
        placeholder="Поиск ученика..."
        class="pl-10 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent w-48"
    >
</form>
```

- [ ] **Step 2: Preserve query state in student links and subject chips**

Заменить ссылки:

```django
<a href="?student_id={{ student.id }}"
```

на:

```django
<a href="?student_id={{ student.id }}{% if search_query %}&q={{ search_query|urlencode }}{% endif %}{% if chart_subject_id %}&subject_id={{ chart_subject_id }}{% endif %}{% if chart_range %}&range={{ chart_range }}{% endif %}"
```

И ссылки subject chips:

```django
<a href="?student_id={{ student.id }}&subject_id={{ profile.subject.id }}&range={{ chart_range|default:30 }}"
```

на:

```django
<a href="?student_id={{ student.id }}&subject_id={{ profile.subject.id }}&range={{ chart_range|default:30 }}{% if search_query %}&q={{ search_query|urlencode }}{% endif %}"
```

- [ ] **Step 3: Add empty state**

Под списком учеников заменить голый цикл на ветвление:

```django
{% if students %}
    {% for student in students %}
        ...
    {% endfor %}
{% else %}
    <div class="bg-white rounded-xl border border-gray-200 px-4 py-6 text-sm text-gray-500 text-center">
        Ученики не найдены
    </div>
{% endif %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
python manage.py test core.tests.test_tutor_dashboard_student_search -v 1
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/templates/core/tutor_dashboard.html
git commit -m "feat: wire tutor dashboard student search form"
```

---

### Task 4: Обновить regression tests на persistence и query state

**Files:**
- Modify: `/workspace/core/tests/test_tutor_selected_student_persists_across_pages.py`
- Test: `/workspace/core/views.py`
- Test: `/workspace/core/templates/core/tutor_dashboard.html`

- [ ] **Step 1: Extend the persistence test**

Заменить сценарий на вариант с query state:

```python
def test_selected_student_persists_with_search_query(self):
    self.client.login(username="t", password="pass")

    r1 = self.client.get(reverse("tutor_dashboard"), {"student_id": self.student2.id, "q": "s2"})
    self.assertEqual(r1.status_code, 200)
    self.assertEqual(self.client.session.get("tutor_selected_student_id"), self.student2.id)

    r2 = self.client.get(reverse("tutor_dashboard"), {"q": "s2"})
    self.assertEqual(r2.status_code, 200)
    self.assertContains(
        r2,
        f'href="?student_id={self.student2.id}&q=s2"',
    )
```

- [ ] **Step 2: Run the updated regression test**

Run:
```bash
python manage.py test core.tests.test_tutor_selected_student_persists_across_pages -v 1
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_tutor_selected_student_persists_across_pages.py
git commit -m "test: preserve tutor selected student with search query"
```

---

### Task 5: Focused regression suite and diagnostics

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`
- Modify: `/workspace/core/tests/test_tutor_selected_student_persists_across_pages.py`
- Create: `/workspace/core/tests/test_tutor_dashboard_student_search.py`

- [ ] **Step 1: Run focused regression suite**

Run:
```bash
python manage.py test \
  core.tests.test_tutor_dashboard_student_search \
  core.tests.test_tutor_selected_student_persists_across_pages \
  core.tests.test_tutor_dashboard_subject_switcher \
  core.tests.test_tutor_dashboard_srs_counters \
  core.tests.test_tutor_dashboard_unread_link_points_to_submission \
  -v 1
```

Expected: PASS

- [ ] **Step 2: Check diagnostics on edited files**

Check diagnostics for:
- `/workspace/core/views.py`
- `/workspace/core/templates/core/tutor_dashboard.html`
- `/workspace/core/tests/test_tutor_dashboard_student_search.py`
- `/workspace/core/tests/test_tutor_selected_student_persists_across_pages.py`

Expected: no new lint/template errors.

- [ ] **Step 3: Final commit**

```bash
git add core/views.py core/templates/core/tutor_dashboard.html core/tests/test_tutor_dashboard_student_search.py core/tests/test_tutor_selected_student_persists_across_pages.py
git commit -m "feat: add tutor dashboard student search"
```

---

## Self-review

- Spec coverage:
  - removal of add button: covered in Task 1 and Task 3
  - server GET search by `q`: covered in Task 2 and Task 3
  - query-state preservation: covered in Task 3 and Task 4
  - empty state and safe fallback: covered in Task 2 and Task 3
- Placeholder scan:
  - no `TODO`, `TBD`, or vague “handle appropriately”
- Type consistency:
  - `search_query`, `student_id`, `subject_id`, `range` use the same names in tests, view, and template
