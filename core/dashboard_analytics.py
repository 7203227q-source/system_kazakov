import json
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from core.models import Submission


def build_weekly_solved_chart_data(student, *, subject_id: int | None, today=None) -> str | None:
    if not subject_id:
        return None

    if today is None:
        today = timezone.localdate()

    start = today - timedelta(days=6)
    qs = (
        Submission.objects.filter(
            student=student,
            task__topic__subject_id=int(subject_id),
        )
        .filter(Q(is_correct__isnull=False) | Q(tutor_primary_score__isnull=False) | Q(primary_score__isnull=False) | Q(score__isnull=False))
        .order_by("created_at")
        .values_list(
            "created_at",
            "task_id",
            "is_correct",
            "tutor_primary_score",
            "primary_score",
            "score",
            "task__exam_points",
            "task__task_type__max_points",
        )
    )

    last_by_day_task: dict[tuple, tuple[float, float]] = {}
    for created_at, task_id, is_correct, tutor_primary_score, primary_score, score, task_exam_points, task_type_max_points in qs:
        d = created_at.date()
        if d < start or d > today:
            continue
        mp = float(int(task_exam_points or 0) if int(task_exam_points or 0) > 0 else int(task_type_max_points or 1))
        if bool(is_correct):
            earned = mp
        else:
            v = tutor_primary_score if tutor_primary_score is not None else primary_score
            v = v if v is not None else score
            earned = float(v or 0)
        last_by_day_task[(d, int(task_id))] = (earned, mp)

    labels: list[str] = []
    correct: list[int] = []
    incorrect: list[int] = []

    for i in range(7):
        day = start + timedelta(days=i)
        labels.append(day.strftime("%d %b"))
        c = 0.0
        w = 0.0
        for (d, _), v in last_by_day_task.items():
            if d != day:
                continue
            earned, mp = v
            c += float(earned)
            w += float(mp - earned)
        correct.append(int(round(c)))
        incorrect.append(int(round(w)))

    return json.dumps({"labels": labels, "correct": correct, "incorrect": incorrect})


def build_submission_summary(student, *, subject_id: int | None) -> dict:
    if not subject_id:
        return {"total": 0, "correct": 0, "incorrect": 0, "correct_rate": None}

    submissions_subject = Submission.objects.filter(student=student, task__topic__subject_id=int(subject_id))
    total = int(submissions_subject.count())

    scored_submissions = submissions_subject.filter(
        Q(is_correct__isnull=False) | Q(tutor_primary_score__isnull=False) | Q(primary_score__isnull=False) | Q(score__isnull=False)
    ).values_list(
        "is_correct",
        "tutor_primary_score",
        "primary_score",
        "score",
        "task__exam_points",
        "task__task_type__max_points",
    )
    max_total = 0.0
    earned_total = 0.0
    for is_correct, tutor_primary_score, primary_score, score, task_exam_points, task_type_max_points in scored_submissions:
        mp = float(int(task_exam_points or 0) if int(task_exam_points or 0) > 0 else int(task_type_max_points or 1))
        if bool(is_correct):
            earned = mp
        else:
            v = tutor_primary_score if tutor_primary_score is not None else primary_score
            v = v if v is not None else score
            earned = float(v or 0)
        max_total += mp
        earned_total += earned

    correct_rate = (earned_total / max_total * 100.0) if max_total > 0 else None
    incorrect_total = max_total - earned_total
    return {"total": total, "correct": earned_total, "incorrect": incorrect_total, "correct_rate": correct_rate}
