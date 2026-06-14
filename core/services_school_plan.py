from datetime import timedelta

from django.utils import timezone

from core.models import PlanItem, StudentLearningPlan


def collect_diagnostic_scores_for_track(*, track, data):
    diagnostic_scores = {}
    for topic_id in track.units.values_list("topics__id", flat=True):
        if not topic_id:
            continue
        raw_score = data.get(f"topic_{topic_id}")
        if raw_score in (None, ""):
            continue
        diagnostic_scores[topic_id] = float(raw_score)
    return diagnostic_scores


def create_initial_learning_plan(*, student, track, diagnostic_scores, goal_type, created_by=None):
    plan = StudentLearningPlan.objects.create(
        student=student,
        learning_track=track,
        goal_type=goal_type,
        status="active",
        diagnostic_completed_at=timezone.now(),
        created_by=created_by,
    )
    ordered_pairs = sorted(diagnostic_scores.items(), key=lambda pair: pair[1])
    max_priority = len(ordered_pairs)
    for index, (topic_id, score) in enumerate(ordered_pairs):
        PlanItem.objects.create(
            plan=plan,
            curriculum_topic_id=topic_id,
            priority=max_priority - index,
            target_mastery="0.80",
            recommended_task_count=7 if score < 0.5 else 5,
            status="assigned",
        )
    return plan


def update_learning_plan_after_result(*, item, accuracy):
    if accuracy < 0.6:
        item.status = "repeat"
        item.next_review_at = timezone.now() + timedelta(days=3)
    elif accuracy >= 0.85:
        item.status = "mastered"
        item.next_review_at = None
    else:
        item.status = "in_progress"
        item.next_review_at = None
    item.save(update_fields=["status", "next_review_at"])
    return item
