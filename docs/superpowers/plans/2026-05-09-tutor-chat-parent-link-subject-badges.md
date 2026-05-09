# Tutor Chat CTA, Parent Invite Code, Subject Badges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать «Назначить задание» из нижнего блока tutor_dashboard, перевести сообщения на внутренний чат, добавить привязку родителя по коду ученика и бейджи предметов для быстрого переключения аналитики.

**Architecture:** Изменения затрагивают только Django templates + несколько view/URL + 1 миграцию для нового поля `parent_invite_code` у ученика. Отправка сообщений — через существующий чат (`views_chat.py`), без внешних мессенджеров.

**Tech Stack:** Django ORM, Django templates, существующий чат (`Message`), миграции Django.

---

## Файлы

**Modify:**
- `/workspace/core/models.py` — добавить поле `parent_invite_code` в `User`.
- `/workspace/core/views.py` — генерация кода, обработка привязки в `parent_dashboard`, вывод в `tutor_dashboard`.
- `/workspace/core/urls.py` — при необходимости новый endpoint (если решим не встраивать POST в existing view).
- `/workspace/core/templates/core/tutor_dashboard.html` — убрать таб «Назначить задание», добавить CTA “Открыть чат”, показать parent-код, бейджи предметов.
- `/workspace/core/templates/core/parent_dashboard.html` — форма ввода кода ученика для привязки (когда детей нет).

**Create:**
- `/workspace/core/migrations/00xx_user_parent_invite_code.py` — миграция на добавление поля.

---

### Task 1: Поле `parent_invite_code` у ученика

**Files:**
- Modify: `/workspace/core/models.py`
- Create: `/workspace/core/migrations/00xx_user_parent_invite_code.py`

- [ ] **Step 1: Добавить поле в модель**

В `User` добавить:

```py
parent_invite_code = models.CharField(max_length=10, unique=True, null=True, blank=True, verbose_name="Код для привязки родителя")
```

- [ ] **Step 2: Создать миграцию**

Run:

```bash
python manage.py makemigrations core
```

Expected: создаст миграцию с добавлением поля.

- [ ] **Step 3: Commit**

```bash
git add core/models.py core/migrations
git commit -m "feat: add parent invite code for students"
```

---

### Task 2: Генерация parent-кода (уникальность) и показ в tutor_dashboard

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`

- [ ] **Step 1: Добавить генератор кода**

В `core/views.py` рядом с `generate_invite_code()` добавить функцию:

```py
def generate_parent_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
```

И helper для уникальности:

```py
def ensure_parent_invite_code(student: User):
    if student.parent_invite_code:
        return
    code = generate_parent_invite_code()
    while User.objects.filter(parent_invite_code=code).exists():
        code = generate_parent_invite_code()
    student.parent_invite_code = code
    student.save(update_fields=['parent_invite_code'])
```

- [ ] **Step 2: В `tutor_dashboard` обеспечить наличие кода**

В ветке `if selected_student:` вызвать `ensure_parent_invite_code(selected_student)` (после получения `selected_student`).

- [ ] **Step 3: Показать код в UI**

В `tutor_dashboard.html` в блоке информации об ученике (рядом с телефоном/кнопками) добавить карточку:

```django
<div class="text-xs text-gray-500">Код для родителя</div>
<div class="flex items-center gap-2">
  <span class="font-mono font-bold tracking-widest">{{ selected_student.parent_invite_code|default:"—" }}</span>
  <button type="button" onclick="navigator.clipboard.writeText('{{ selected_student.parent_invite_code|default:"" }}')" ...>Скопировать</button>
</div>
```

- [ ] **Step 4: Smoke-check**

```bash
python -m compileall -q /workspace/core
```

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/templates/core/tutor_dashboard.html
git commit -m "feat: show parent invite code in tutor dashboard"
```

---

### Task 3: Привязка родителя к ученику по коду (parent_dashboard)

**Files:**
- Modify: `/workspace/core/views.py`
- Modify: `/workspace/core/templates/core/parent_dashboard.html`

- [ ] **Step 1: Обработка POST в `parent_dashboard`**

В `parent_dashboard` добавить:
- проверку `request.user.role == 'parent'`
- если POST и есть поле `student_code`:
  - нормализуем: `code = request.POST.get('student_code','').strip().upper()`
  - `student = User.objects.get(parent_invite_code=code, role='student')`
  - `request.user.children.add(student)` и `messages.success(...)`
  - если нет — `messages.error(...)`
  - редирект обратно на `parent_dashboard`

- [ ] **Step 2: Форма в шаблоне, когда детей нет**

В `parent_dashboard.html` в блоке “Нет привязанных учеников” добавить форму:

```django
<form method="POST" class="mt-4 ...">
  {% csrf_token %}
  <input name="student_code" ... placeholder="Код ученика" class="uppercase font-mono">
  <button type="submit" ...>Привязать</button>
</form>
```

- [ ] **Step 3: Smoke-check**

```bash
python -m compileall -q /workspace/core
```

- [ ] **Step 4: Commit**

```bash
git add core/views.py core/templates/core/parent_dashboard.html
git commit -m "feat: parent can link student by invite code"
```

---

### Task 4: Убрать «Назначить задание», оставить сообщения (переход в чат)

**Files:**
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`

- [ ] **Step 1: Удалить таб «Назначить задание»**

Удалить кнопку/вкладку и соответствующий контент.

- [ ] **Step 2: «Сообщение ученику» → переход в чат**

Сделать кнопку:

```django
<a href="{% url 'chat_dialog' selected_student.id %}" ...>Открыть чат</a>
```

- [ ] **Step 3: «Сообщение родителю» → переход в чат**

Если `selected_student.parents.count == 1`:
- ссылка на `chat_dialog parent.id`

Если родителей несколько:
- select + кнопка “Открыть чат” (GET на тот же `chat_dialog`).

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/tutor_dashboard.html
git commit -m "feat: replace tutor dashboard messaging tabs with chat links"
```

---

### Task 5: Бейджи предметов у ученика + быстрый выбор предмета у репетитора

**Files:**
- Modify: `/workspace/core/templates/core/tutor_dashboard.html`

- [ ] **Step 1: В карточке ученика слева добавить бейджи предметов**

Использовать `student.subject_profiles.all` и выводить `profile.subject.name` как chips.

Каждый chip — ссылка вида:

```django
?student_id={{ student.id }}&subject_id={{ profile.subject.id }}&range={{ chart_range|default:30 }}
```

Активный subject подсвечивать (если `chart_subject_id == profile.subject.id` и `selected_student.id == student.id`).

- [ ] **Step 2: Smoke-check**

```bash
python -m compileall -q /workspace/core
```

- [ ] **Step 3: Commit**

```bash
git add core/templates/core/tutor_dashboard.html
git commit -m "feat: subject badges and quick analytics switch in tutor student list"
```

---

### Task 6: Push

- [ ] **Step 1: Push**

```bash
git push origin main
```

---

## Self-review (перед пушем)

- Убедиться, что `parent_invite_code` генерируется только для студентов.
- Убедиться, что формы используют POST + CSRF.
- Убедиться, что ссылки на чат работают (роуты `urls_chat.py` подключены в проекте).

