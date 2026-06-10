from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Any

from fsrs import Card, Rating, Scheduler


SCHEDULER = Scheduler(enable_fuzzing=False)


def load_card(fsrs_state: dict[str, Any] | None) -> Card:
    if fsrs_state:
        return Card.from_dict(fsrs_state)
    return Card()


def rating_from_label(label: str) -> Rating:
    mapping = {
        "again": Rating.Again,
        "hard": Rating.Hard,
        "good": Rating.Good,
    }
    return mapping[label]


def review_card(fsrs_state: dict[str, Any] | None, label: str) -> dict[str, Any]:
    card = load_card(fsrs_state)
    reviewed_card, _review_log = SCHEDULER.review_card(
        card=card,
        rating=rating_from_label(label),
        review_datetime=datetime.now(dt_timezone.utc),
    )
    return reviewed_card.to_dict()
