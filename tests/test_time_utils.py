from datetime import datetime, timedelta, timezone
import unittest

from session_memory.time_utils import resolve_time_range, strip_time_terms


KST = timezone(timedelta(hours=9))


class TimeUtilsTests(unittest.TestCase):
    def test_resolves_yesterday_three_oclock(self):
        now = datetime(2026, 6, 13, 10, 0, tzinfo=KST)

        start, end = resolve_time_range("어제 3시", now=now)

        self.assertEqual(start.isoformat(), "2026-06-12T03:00:00+09:00")
        self.assertEqual(end.isoformat(), "2026-06-12T03:59:59+09:00")

    def test_resolves_yesterday_without_hour_to_full_day(self):
        now = datetime(2026, 6, 13, 10, 0, tzinfo=KST)

        start, end = resolve_time_range("어제", now=now)

        self.assertEqual(start.isoformat(), "2026-06-12T00:00:00+09:00")
        self.assertEqual(end.isoformat(), "2026-06-12T23:59:59+09:00")

    def test_empty_query_defaults_to_wide_range(self):
        now = datetime(2026, 6, 13, 10, 0, tzinfo=KST)

        start, end = resolve_time_range("", now=now)

        self.assertEqual(start.isoformat(), "1970-01-01T00:00:00+09:00")
        self.assertEqual(end.isoformat(), "2026-06-13T10:00:00+09:00")

    def test_strip_time_terms_keeps_topic_terms(self):
        self.assertEqual(strip_time_terms("어제 3시 pipeline 어디까지"), "pipeline 어디까지")


if __name__ == "__main__":
    unittest.main()

