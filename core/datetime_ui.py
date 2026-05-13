from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone


def format_ui_datetime(dt: datetime | None, now: datetime | None = None, tz_name: str = "Europe/Moscow") -> str:
    """
    Форматирует datetime для UI:
    - сегодня HH:MM
    - вчера HH:MM
    - DD.MM HH:MM (если год текущий)
    - DD.MM.YYYY HH:MM (если год не текущий)
    """
    if not dt:
        return ""

    tz = ZoneInfo(tz_name)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, tz)
    local_dt = timezone.localtime(dt, tz)

    now_dt = now or timezone.now()
    if timezone.is_naive(now_dt):
        now_dt = timezone.make_aware(now_dt, tz)
    local_now = timezone.localtime(now_dt, tz)

    if local_dt.date() == local_now.date():
        return f"сегодня {local_dt:%H:%M}"
    if local_dt.date() == (local_now.date() - timedelta(days=1)):
        return f"вчера {local_dt:%H:%M}"

    if local_dt.year != local_now.year:
        return f"{local_dt:%d.%m.%Y %H:%M}"
    return f"{local_dt:%d.%m %H:%M}"

