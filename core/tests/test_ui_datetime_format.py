from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase


class UIDatetimeFormatTests(TestCase):
    def test_today(self):
        from core.datetime_ui import format_ui_datetime

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 10, 0, tzinfo=tz)
        dt = datetime(2026, 5, 13, 9, 5, tzinfo=tz)
        self.assertEqual(format_ui_datetime(dt, now=now), "сегодня 09:05")

    def test_yesterday(self):
        from core.datetime_ui import format_ui_datetime

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 10, 0, tzinfo=tz)
        dt = datetime(2026, 5, 12, 21, 10, tzinfo=tz)
        self.assertEqual(format_ui_datetime(dt, now=now), "вчера 21:10")

    def test_other_date_current_year(self):
        from core.datetime_ui import format_ui_datetime

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 10, 0, tzinfo=tz)
        dt = datetime(2026, 4, 2, 8, 0, tzinfo=tz)
        self.assertEqual(format_ui_datetime(dt, now=now), "02.04 08:00")

    def test_other_date_other_year(self):
        from core.datetime_ui import format_ui_datetime

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 10, 0, tzinfo=tz)
        dt = datetime(2025, 12, 31, 23, 59, tzinfo=tz)
        self.assertEqual(format_ui_datetime(dt, now=now), "31.12.2025 23:59")
