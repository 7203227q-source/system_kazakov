from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.template import Context, Template
from django.test import TestCase


class TimeGreetingTests(TestCase):
    def test_night_end_boundary(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 4, 59, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Доброй ночи")

    def test_morning_start_boundary(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 5, 0, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Доброе утро")

    def test_morning_end_boundary(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 11, 59, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Доброе утро")

    def test_day_start_boundary(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 12, 0, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Добрый день")

    def test_day_end_boundary(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 17, 59, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Добрый день")

    def test_evening_start_boundary(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 13, 18, 0, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Добрый вечер")

    def test_midnight_is_night(self):
        from core.greetings import get_time_greeting

        tz = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 5, 14, 0, 0, tzinfo=tz)
        self.assertEqual(get_time_greeting(now=now), "Доброй ночи")

    def test_template_tag_renders(self):
        tz = ZoneInfo("Europe/Moscow")
        mocked_now = datetime(2026, 5, 13, 12, 0, tzinfo=tz)

        with patch("core.greetings.timezone.now", return_value=mocked_now):
            tpl = Template("{% load time_greeting %}{% time_greeting %}")
            self.assertEqual(tpl.render(Context({})), "Добрый день")
