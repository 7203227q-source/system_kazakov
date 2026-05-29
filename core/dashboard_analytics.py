import json
from datetime import timedelta

from django.utils import timezone

from core.models import Submission


def build_weekly_solved_chart_data(student, *, subject_id: int | None, today=None) -> str | None:
    if not subject_id:
        return None

    if today is None:
        today = timezone.localdate()

    start = today - timedelta(days=6)
    rows = (
        Submission.objects.filter(
            student=student,
            created_at__date__gte=start,
            created_at__date__lte=today,
            task__topic__subject_id=int(subject_id),
        )
        .order_by("created_at")
        .values_list("created_at__date", "task_id", "is_correct")
    )

    last_by_day_task: dict[tuple, bool] = {}
    for d, task_id, is_correct in rows:
        last_by_day_task[(d, int(task_id))] = bool(is_correct)

    labels: list[str] = []
    correct: list[int] = []
    incorrect: list[int] = []

    for i in range(7):
        day = start + timedelta(days=i)
        labels.append(day.strftime("%d %b"))
        c = 0
        w = 0
        for (d, _), ok in last_by_day_task.items():
            if d != day:
                continue
            if ok:
                c += 1
            else:
                w += 1
        correct.append(c)
        incorrect.append(w)

    return json.dumps({"labels": labels, "correct": correct, "incorrect": incorrect})


def build_submission_summary(student, *, subject_id: int | None) -> dict:
    if not subject_id:
        return {"total": 0, "correct": 0, "incorrect": 0, "correct_rate": None}

    qs = Submission.objects.filter(student=student, task__topic__subject_id=int(subject_id))
    total = int(qs.count())
    correct = int(qs.filter(is_correct=True).count())
    incorrect = int(total - correct)
    correct_rate = int(round((correct / total) * 100)) if total > 0 else None
    return {"total": total, "correct": correct, "incorrect": incorrect, "correct_rate": correct_rate}

