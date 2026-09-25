"""Verify the accepted schedule-snapshot-selection decision (2026-09-24)."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth.select_schedule_snapshot import select_schedule_snapshot


AGENCY_TIMEZONE = "America/New_York"
SERVICE_DATE = date(2026, 9, 22)


def snapshot(content="a", receipt=None):
    return {
        "zip_sha256": content * 64,
        "downloaded_at_utc": receipt or datetime(2026, 9, 10, tzinfo=timezone.utc),
        "feed_start_date": date(2026, 1, 1),
        "feed_end_date": date(2026, 12, 31),
    }


class SelectScheduleSnapshotTests(unittest.TestCase):
    def assert_unresolved(self, snapshots):
        result = select_schedule_snapshot(SERVICE_DATE, snapshots, AGENCY_TIMEZONE)
        self.assertEqual(result["status"], "unresolved")
        self.assertTrue(result.get("reason"))
        self.assertNotIn("snapshot", result)

    def test_newer_eligible_b_wins_regardless_of_input_order(self):
        a = snapshot()
        b = snapshot("b", datetime(2026, 9, 20, tzinfo=timezone.utc))
        for rows in ([a, b], [b, a]):
            with self.subTest(order=[row["zip_sha256"] for row in rows]):
                self.assertEqual(select_schedule_snapshot(SERVICE_DATE, rows, AGENCY_TIMEZONE),
                                 {"status": "selected", "snapshot": b})

    def test_exact_local_midnight_is_eligible_in_summer_and_winter(self):
        # Independent UTC expectations: New York midnight is 04:00 in September,
        # 05:00 in January. Do not derive the oracle with the selector's logic.
        for day, cutoff in [
            (SERVICE_DATE, datetime(2026, 9, 22, 4, tzinfo=timezone.utc)),
            (date(2026, 1, 22), datetime(2026, 1, 22, 5, tzinfo=timezone.utc)),
        ]:
            with self.subTest(day=day):
                a = snapshot("a", cutoff - timedelta(days=1))
                b = snapshot("b", cutoff)
                self.assertEqual(select_schedule_snapshot(day, [a, b], AGENCY_TIMEZONE),
                                 {"status": "selected", "snapshot": b})

    def test_one_microsecond_after_local_midnight_is_ineligible(self):
        for day, cutoff in [
            (SERVICE_DATE, datetime(2026, 9, 22, 4, tzinfo=timezone.utc)),
            (date(2026, 1, 22), datetime(2026, 1, 22, 5, tzinfo=timezone.utc)),
        ]:
            with self.subTest(day=day):
                a = snapshot("a", cutoff - timedelta(microseconds=1))
                b = snapshot("b", cutoff + timedelta(microseconds=1))
                self.assertEqual(select_schedule_snapshot(day, [b, a], AGENCY_TIMEZONE),
                                 {"status": "selected", "snapshot": a})

    def test_none_qualifies(self):
        self.assert_unresolved([])
        self.assert_unresolved([snapshot(receipt=datetime(2026, 9, 22, 4, 0, 0, 1, tzinfo=timezone.utc))])

    def test_coverage_boundaries_are_inclusive(self):
        for start, end in [(SERVICE_DATE, date(2026, 9, 30)),
                           (date(2026, 9, 1), SERVICE_DATE), (SERVICE_DATE, SERVICE_DATE)]:
            with self.subTest(start=start, end=end):
                row = snapshot()
                row.update(feed_start_date=start, feed_end_date=end)
                self.assertEqual(select_schedule_snapshot(SERVICE_DATE, [row], AGENCY_TIMEZONE),
                                 {"status": "selected", "snapshot": row})

    def test_missing_coverage_keys_are_ineligible(self):
        for fields in [("feed_start_date",), ("feed_end_date",),
                       ("feed_start_date", "feed_end_date")]:
            for with_fallback in (False, True):
                with self.subTest(fields=fields, with_fallback=with_fallback):
                    bad = snapshot("b", datetime(2026, 9, 20, tzinfo=timezone.utc))
                    for field in fields:
                        del bad[field]
                    if with_fallback:
                        good = snapshot()
                        self.assertEqual(select_schedule_snapshot(SERVICE_DATE, [bad, good], AGENCY_TIMEZONE),
                                         {"status": "selected", "snapshot": good})
                    else:
                        self.assert_unresolved([bad])

    def test_unknown_or_invalid_coverage_values_are_ineligible(self):
        for field in ("feed_start_date", "feed_end_date"):
            for value in (None, "", "2026-02-30", "20260922", 20260922,
                          datetime(2026, 9, 22, tzinfo=timezone.utc)):
                with self.subTest(field=field, value=value):
                    bad = snapshot("b", datetime(2026, 9, 20, tzinfo=timezone.utc))
                    bad[field] = value
                    self.assert_unresolved([bad])
                    good = snapshot()
                    self.assertEqual(select_schedule_snapshot(SERVICE_DATE, [bad, good], AGENCY_TIMEZONE),
                                     {"status": "selected", "snapshot": good})

    def test_reversed_and_out_of_range_coverage_are_ineligible(self):
        for start, end in [(date(2026, 9, 23), date(2026, 9, 21)),
                           (date(2026, 9, 23), date(2026, 9, 30)),
                           (date(2026, 9, 1), date(2026, 9, 21))]:
            with self.subTest(start=start, end=end):
                bad = snapshot("b", datetime(2026, 9, 20, tzinfo=timezone.utc))
                bad.update(feed_start_date=start, feed_end_date=end)
                self.assert_unresolved([bad])
                good = snapshot()
                self.assertEqual(select_schedule_snapshot(SERVICE_DATE, [bad, good], AGENCY_TIMEZONE),
                                 {"status": "selected", "snapshot": good})

    def test_invalid_receipt_types_and_timezones_raise_value_error(self):
        for receipt in (date(2026, 9, 20), "2026-09-20",
                        datetime(2026, 9, 20),
                        datetime(2026, 9, 20, tzinfo=timezone(timedelta(hours=-4))),
                        datetime(2026, 9, 20, tzinfo=timezone(timedelta(hours=1)))):
            with self.subTest(receipt=receipt):
                with self.assertRaises(ValueError):
                    select_schedule_snapshot(SERVICE_DATE, [snapshot(receipt=receipt)], AGENCY_TIMEZONE)


if __name__ == "__main__":
    unittest.main()
