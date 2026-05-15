# Chat “Ждёт ответа” Badge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В чате у репетитора помечать диалоги, где последнее сообщение написал не репетитор (то есть диалог “ждёт ответа”).

**Architecture:** Флаг “ждёт ответа” вычисляется в `get_user_dialogs()` вместе с `last_message` и передаётся в шаблон `chat.html`, где рисуется небольшой бейдж в списке диалогов.

**Tech Stack:** Django, Django ORM, Django templates, Django TestCase

---

### Task 1: Add “needs_reply” flag to dialogs

**Files:**
- Modify: [views_chat.py](file:///workspace/core/views_chat.py)

- [ ] **Step 1: Write a failing test**

Create `core/tests/test_chat_needs_reply_badge.py`:

```python
from django.test import TestCase
from django.urls import reverse

from core.models import Message, TutorStudentLink, User


class ChatNeedsReplyBadgeTests(TestCase):
    def test_tutor_sees_needs_reply_badge_when_last_message_from_student(self):
        tutor = User.objects.create_user(username="tutor1", password="pw", role="tutor")
        student = User.objects.create_user(username="student1", password="pw", role="student")
        TutorStudentLink.objects.create(tutor=tutor, student=student)

        Message.objects.create(sender=student, receiver=tutor, content="Привет", is_read=True)

        self.client.force_login(tutor)
        response = self.client.get(reverse("chat_index"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ждёт ответа")

    def test_tutor_does_not_see_needs_reply_badge_when_last_message_from_tutor(self):
        tutor = User.objects.create_user(username="tutor2", password="pw", role="tutor")
        student = User.objects.create_user(username="student2", password="pw", role="student")
        TutorStudentLink.objects.create(tutor=tutor, student=student)

        Message.objects.create(sender=student, receiver=tutor, content="Привет", is_read=True)
        Message.objects.create(sender=tutor, receiver=student, content="Ответил", is_read=True)

        self.client.force_login(tutor)
        response = self.client.get(reverse("chat_index"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Ждёт ответа")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python manage.py test core.tests.test_chat_needs_reply_badge -v 2
```

Expected: FAIL (пока нет бейджа и/или поля в контексте).

- [ ] **Step 3: Implement minimal code in `get_user_dialogs()`**

Update `core/views_chat.py` to add `needs_reply`:

```python
needs_reply = False
if user.role == "tutor" and last_msg and last_msg.sender_id != user.id:
    needs_reply = True

enriched_dialogs.append({
    "user": other_user,
    "last_message": last_msg,
    "unread_count": unread_count,
    "needs_reply": needs_reply,
    "sort_date": last_msg.created_at if last_msg else timezone.datetime.min.replace(tzinfo=timezone.UTC),
})
```

- [ ] **Step 4: Run tests to verify it still fails on template (until Task 2)**

Run:

```bash
python manage.py test core.tests.test_chat_needs_reply_badge -v 2
```

Expected: still FAIL until the template prints the badge.

---

### Task 2: Render “Ждёт ответа” badge in chat dialogs list

**Files:**
- Modify: [chat.html](file:///workspace/core/templates/core/chat.html)

- [ ] **Step 1: Update template to render the badge**

In the dialogs list item, near timestamp (inside the `if d.last_message` block), render:

```django
{% if user.role == 'tutor' and d.needs_reply %}
<span class="ml-2 bg-amber-100 text-amber-800 text-[10px] font-bold px-2 py-0.5 rounded-full whitespace-nowrap">Ждёт ответа</span>
{% endif %}
```

- [ ] **Step 2: Run tests to verify they pass**

Run:

```bash
python manage.py test core.tests.test_chat_needs_reply_badge -v 2
```

Expected: PASS

- [ ] **Step 3: Run a broader smoke test**

Run:

```bash
python manage.py test core.tests.test_chat_send_form_visible -v 2
```

Expected: PASS

