from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone


def get_time_greeting(now: datetime | None = None, tz_name: str = "Europe/Moscow") -> str:
    tz = ZoneInfo(tz_name)
    now_dt = now or timezone.now()

    if timezone.is_naive(now_dt):
        now_dt = timezone.make_aware(now_dt, tz)

    local_now = timezone.localtime(now_dt, tz)
    hour = local_now.hour

    if 0 <= hour <= 4:
        return "Доброй ночи"
    if 5 <= hour <= 11:
        return "Доброе утро"
    if 12 <= hour <= 17:
        return "Добрый день"
    return "Добрый вечер"
