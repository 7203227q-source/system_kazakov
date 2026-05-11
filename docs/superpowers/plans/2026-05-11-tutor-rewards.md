# Tutor Rewards (XP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить награды от репетитора: вручную начислять ученику XP по предмету с историей начислений и UI в кабинете репетитора.

**Architecture:** Новая модель `TutorReward` хранит записи начислений. POST-эндпоинт валидирует права репетитора и обновляет `StudentSubjectProfile.xp/level`. В `tutor_dashboard.html` добавляется форма начисления и список последних наград.

**Tech Stack:** Django ORM, существующие `core/views.py`, `core/models.py`, шаблоны.

---

## File Map

**Create**
- `core/tests/test_tutor_rewards.py`
- `core/migrations/0037_tutorreward.py`

**Modify**
- `core/models.py`
- `core/views.py`
- `core/urls.py`
- `core/templates/core/tutor_dashboard.html`

---

### Task 1: Add failing tests (RED)

**Files:**
- Create: `core/tests/test_tutor_rewards.py`

- [ ] **Step 1: Write failing tests**

```python
from django.test import TestCase
from django.urls import reverse

from core.models import ExamFormat, Subject, StudentSubjectProfile, User


class TutorRewardsTests(TestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(username="t", password="pass", role="tutor")
        self.student = User.objects.create_user(username="s", password="pass", role="student")
        self.other_tutor = User.objects.create_user(username="t2", password="pass", role="tutor")
        self.tutor.students.add(self.student)
        self.subject = Subject.objects.create(name="Математика")
        ExamFormat.objects.create(subject=self.subject, name="ОГЭ математика", year=2026, is_active=True)
        self.profile = StudentSubjectProfile.objects.create(student=self.student, subject=self.subject, xp=0, level=1, target_score=80)

    def test_tutor_can_award_xp_to_student_subject(self):
        self.client.login(username="t", password="pass")
        res = self.client.post(reverse("tutor_award_xp"), {"student_id": str(self.student.id), "subject_id": str(self.subject.id), "xp_amount": "50", "reason": "Молодец"})
        self.assertEqual(res.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.xp, 50)
        self.assertEqual(self.profile.level, 1)
        from core.models import TutorReward
        self.assertEqual(TutorReward.objects.count(), 1)

    def test_other_tutor_cannot_award(self):
        self.client.login(username="t2", password="pass")
        res = self.client.post(reverse("tutor_award_xp"), {"student_id": str(self.student.id), "subject_id": str(self.subject.id), "xp_amount": "50"})
        self.assertEqual(res.status_code, 403)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.xp, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
python manage.py test core.tests.test_tutor_rewards -v 1
```

Expected: FAIL (нет модели/вьюхи/URL).

---

### Task 2: Add TutorReward model + migration (GREEN)

**Files:**
- Modify: `core/models.py`
- Create: `core/migrations/0037_tutorreward.py`

- [ ] **Step 1: Add model**

```python
class TutorReward(models.Model):
    tutor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="given_rewards")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_rewards")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="rewards")
    xp_amount = models.PositiveIntegerField()
    reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

- [ ] **Step 2: Create migration**

Run:
```bash
python manage.py makemigrations core
```

- [ ] **Step 3: Run tests (still failing)**

Run:
```bash
python manage.py test core.tests.test_tutor_rewards -v 1
```

Expected: still FAIL (нет endpoint).

---

### Task 3: Implement award endpoint + URL (GREEN)

**Files:**
- Modify: `core/views.py`
- Modify: `core/urls.py`
- Test: `core/tests/test_tutor_rewards.py`

- [ ] **Step 1: Add view**

```python
@login_required
@require_POST
def tutor_award_xp(request):
    if request.user.role != "tutor":
        return HttpResponse(status=403)
    student_id_raw = (request.POST.get("student_id") or "").strip()
    subject_id_raw = (request.POST.get("subject_id") or "").strip()
    xp_raw = (request.POST.get("xp_amount") or "").strip()
    reason = (request.POST.get("reason") or "").strip()
    if not (student_id_raw.isdigit() and subject_id_raw.isdigit() and xp_raw.isdigit()):
        return HttpResponse(status=400)
    xp = int(xp_raw)
    if xp < 1 or xp > 500:
        return HttpResponse(status=400)

    student_id = int(student_id_raw)
    subject_id = int(subject_id_raw)
    if not request.user.students.filter(id=student_id).exists():
        return HttpResponse(status=403)

    profile = StudentSubjectProfile.objects.filter(student_id=student_id, subject_id=subject_id).first()
    if profile is None:
        return HttpResponse(status=400)

    from core.models import TutorReward
    TutorReward.objects.create(tutor=request.user, student_id=student_id, subject_id=subject_id, xp_amount=xp, reason=reason[:500])
    profile.xp = int(profile.xp or 0) + xp
    profile.level = (int(profile.xp) // 100) + 1
    profile.save(update_fields=["xp", "level"])
    return redirect(f"{reverse('tutor_dashboard')}?student_id={student_id}")
```

- [ ] **Step 2: Add URL**

```python
path("tutor/award-xp/", views.tutor_award_xp, name="tutor_award_xp"),
```

- [ ] **Step 3: Run tests**

Run:
```bash
python manage.py test core.tests.test_tutor_rewards -v 1
```

Expected: PASS.

---

### Task 4: Add UI on tutor dashboard (REFACTOR)

**Files:**
- Modify: `core/views.py` (подготовить `recent_rewards`)
- Modify: `core/templates/core/tutor_dashboard.html`

- [ ] **Step 1: Query rewards in view**

In `tutor_dashboard`, when `selected_student` present:
- fetch `TutorReward` last 10 for that student
- pass to template as `recent_rewards`

- [ ] **Step 2: Add form & list**

Replace/extend existing “Дать +50 XP” button:
- add `<form method="POST" action="{% url 'tutor_award_xp' %}">` with csrf, hidden student_id, subject select, xp input, reason input, submit
- render `recent_rewards` list below

---

### Task 5: Full suite + commit + push

- [ ] Run:
```bash
python manage.py test core.tests -v 1
```

- [ ] Commit + push:
```bash
git add core/models.py core/migrations core/views.py core/urls.py core/templates/core/tutor_dashboard.html core/tests/test_tutor_rewards.py docs/superpowers/specs/2026-05-11-tutor-rewards-design.md docs/superpowers/plans/2026-05-11-tutor-rewards.md
git commit -m "feat: add tutor XP rewards with history"
git push origin main_sync:main
```

