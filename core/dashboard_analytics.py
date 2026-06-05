import json
from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from core.models import Submission, TaskType


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
            "tutor_scored_at",
            "ai_last_verify_at",
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
    for created_at, tutor_scored_at, ai_last_verify_at, task_id, is_correct, tutor_primary_score, primary_score, score, task_exam_points, task_type_max_points in qs:
        dt = tutor_scored_at or ai_last_verify_at or created_at
        d = dt.date()
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


def build_task_type_rates(student, *, subject_id: int | None, exam_format, today=None) -> tuple[list[dict], str | None]:
    if not subject_id or not exam_format:
        return ([], None)

    if today is None:
        today = timezone.localdate()

    active_exam_format_label = f"{exam_format.name} {exam_format.year}"

    submissions_base = (
        Submission.objects.filter(student=student, task__topic__subject_id=int(subject_id))
        .filter(task__task_type__exam_format=exam_format)
        .exclude(task__task_type__number__isnull=True)
    )

    scored_filter = (
        models.Q(is_correct__isnull=False)
        | models.Q(tutor_primary_score__isnull=False)
        | models.Q(primary_score__isnull=False)
        | models.Q(score__isnull=False)
    )
    submissions_scored = submissions_base.filter(scored_filter)

    latest_id_subq = (
        submissions_scored.filter(task_id=OuterRef("task_id"))
        .order_by("-created_at", "-id")
        .values("id")[:1]
    )
    latest_rows = (
        submissions_scored.annotate(latest_id=Subquery(latest_id_subq))
        .filter(id=models.F("latest_id"))
        .select_related("task", "task__task_type")
        .values(
            "task__task_type__number",
            "created_at",
            "is_correct",
            "tutor_primary_score",
            "primary_score",
            "score",
            "task__exam_points",
            "task__task_type__max_points",
        )
    )

    half_life_days = 14.0
    agg: dict[int, dict] = {}
    for r in latest_rows:
        n = int(r["task__task_type__number"])
        created_at = r["created_at"]
        age_days = max(0, (today - created_at.date()).days)
        weight = 0.5 ** (float(age_days) / float(half_life_days))

        mp = int(r["task__exam_points"] or 0)
        if mp <= 0:
            mp = int(r["task__task_type__max_points"] or 1)
        mp = max(1, int(mp))

        if bool(r["is_correct"]):
            earned = float(mp)
        else:
            v = r["tutor_primary_score"]
            if v is None:
                v = r["primary_score"]
            if v is None:
                v = r["score"]
            earned = float(v or 0)

        frac = earned / float(mp) if mp > 0 else 0.0
        frac = max(0.0, min(1.0, float(frac)))

        a = agg.setdefault(n, {"wt": 0.0, "ws": 0.0, "total": 0.0, "correct": 0.0})
        a["wt"] += float(weight)
        a["ws"] += float(weight) * float(frac)
        a["total"] += float(mp)
        a["correct"] += float(earned)

    numbers = list(
        TaskType.objects.filter(exam_format=exam_format).values_list("number", flat=True).order_by("number")
    )
    numbers = [int(n) for n in numbers if n is not None]

    task_type_name_map = {
        int(t.number): (t.name or "") for t in TaskType.objects.filter(exam_format=exam_format).only("number", "name")
    }

    task_type_rates: list[dict] = []
    for n in numbers:
        a = agg.get(int(n))
        if not a or float(a.get("wt") or 0.0) <= 0:
            task_type_rates.append(
                {"number": n, "name": task_type_name_map.get(n, ""), "rate": None, "total": 0, "correct": 0}
            )
            continue
        rate = (float(a["ws"]) / float(a["wt"]) * 100.0) if float(a["wt"]) > 0 else None
        task_type_rates.append(
            {
                "number": n,
                "name": task_type_name_map.get(n, ""),
                "rate": rate,
                "total": int(round(float(a["total"]))),
                "correct": int(round(float(a["correct"]))),
            }
        )

    return (task_type_rates, active_exam_format_label)
