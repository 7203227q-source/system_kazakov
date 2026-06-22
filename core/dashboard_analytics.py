import json
from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import Submission, TaskLog, TaskType

TASK_TYPE_RATE_RETROSPECTIVE_DAYS = (50, 32, 16, 8, 4)


def build_weekly_solved_chart_data(student, *, subject_id: int | None, today=None) -> str | None:
    if not subject_id:
        return None

    if today is None:
        today = timezone.localdate()

    start = today - timedelta(days=6)
    log_qs = (
        TaskLog.objects.filter(
            student=student,
            task__topic__subject_id=int(subject_id),
            created_at__date__gte=start,
            created_at__date__lte=today,
            is_anomaly=False,
            time_spent__gt=0,
        ).values_list("created_at", "time_spent")
    )
    seconds_by_day: dict[object, int] = {}
    for created_at, time_spent in log_qs:
        d = created_at.date()
        seconds_by_day[d] = int(seconds_by_day.get(d, 0)) + int(time_spent or 0)
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
    minutes: list[int] = []

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
        minutes.append(int(round(float(seconds_by_day.get(day, 0)) / 60.0)))

    return json.dumps({"labels": labels, "correct": correct, "incorrect": incorrect, "minutes": minutes})


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


def _task_type_rate_effective_dt(row) -> object:
    return row["tutor_scored_at"] or row["ai_last_verify_at"] or row["created_at"]


def _task_type_rate_points(row) -> tuple[int, float]:
    mp = int(row["task__exam_points"] or 0)
    if mp <= 0:
        mp = int(row["task__task_type__max_points"] or 1)
    mp = max(1, int(mp))

    if bool(row["is_correct"]):
        earned = float(mp)
    else:
        v = row["tutor_primary_score"]
        if v is None:
            v = row["primary_score"]
        if v is None:
            v = row["score"]
        earned = float(v or 0)

    return mp, earned


def _build_task_type_rate_snapshot(rows: list[dict], *, anchor_day, half_life_days: float) -> dict[int, dict]:
    latest_by_task: dict[int, dict] = {}
    for row in rows:
        effective_dt = _task_type_rate_effective_dt(row)
        if not effective_dt or effective_dt.date() > anchor_day:
            continue

        task_id = int(row["task_id"])
        current = latest_by_task.get(task_id)
        if current is None or _task_type_rate_effective_dt(current) <= effective_dt:
            latest_by_task[task_id] = row

    agg: dict[int, dict] = {}
    for row in latest_by_task.values():
        number = int(row["task__task_type__number"])
        effective_dt = _task_type_rate_effective_dt(row)
        age_days = max(0, (anchor_day - effective_dt.date()).days)
        weight = 0.5 ** (float(age_days) / float(half_life_days))
        mp, earned = _task_type_rate_points(row)
        frac = earned / float(mp) if mp > 0 else 0.0
        frac = max(0.0, min(1.0, float(frac)))

        bucket = agg.setdefault(number, {"wt": 0.0, "ws": 0.0, "total": 0.0, "correct": 0.0})
        bucket["wt"] += float(weight)
        bucket["ws"] += float(weight) * float(frac)
        bucket["total"] += float(mp)
        bucket["correct"] += float(earned)

    return agg


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

    rows = list(
        submissions_scored.values(
            "task_id",
            "task__task_type__number",
            "created_at",
            "tutor_scored_at",
            "ai_last_verify_at",
            "is_correct",
            "tutor_primary_score",
            "primary_score",
            "score",
            "task__exam_points",
            "task__task_type__max_points",
        )
    )

    half_life_days = 21.0
    agg = _build_task_type_rate_snapshot(rows, anchor_day=today, half_life_days=half_life_days)
    retrospective_agg = {
        days: _build_task_type_rate_snapshot(
            rows,
            anchor_day=today - timedelta(days=days),
            half_life_days=half_life_days,
        )
        for days in TASK_TYPE_RATE_RETROSPECTIVE_DAYS
    }

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
        retrospective = []
        for days in TASK_TYPE_RATE_RETROSPECTIVE_DAYS:
            snapshot = retrospective_agg[days].get(int(n))
            retrospective.append(
                {
                    "days_ago": days,
                    "rate": (float(snapshot["ws"]) / float(snapshot["wt"]) * 100.0)
                    if snapshot and float(snapshot.get("wt") or 0.0) > 0
                    else None,
                }
            )
        if not a or float(a.get("wt") or 0.0) <= 0:
            task_type_rates.append(
                {
                    "number": n,
                    "name": task_type_name_map.get(n, ""),
                    "rate": None,
                    "total": 0,
                    "correct": 0,
                    "retrospective": retrospective,
                }
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
                "retrospective": retrospective,
            }
        )

    return (task_type_rates, active_exam_format_label)
