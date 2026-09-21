"""Characterize normalized date rows; CSV coercion/conflicting exceptions are unspecified."""

from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth.gtfs_date import active_service_ids


DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def calendar(service_id, **overrides):
    row = dict.fromkeys(DAYS, 1)
    row.update(service_id=service_id, start_date=date(2026, 9, 21), end_date=date(2026, 9, 27))
    row.update(overrides)
    return row


class ActiveServiceIdsTests(unittest.TestCase):
    def test_each_weekday_selects_only_its_enabled_service(self):
        rows = [calendar(day, **{name: int(name == day) for name in DAYS}) for day in DAYS]
        for offset, day in enumerate(DAYS):
            with self.subTest(day=day):
                self.assertEqual(active_service_ids(date(2026, 9, 21) + timedelta(days=offset), rows, []), {day})

    def test_date_range_is_inclusive_and_excludes_adjacent_dates(self):
        for day, expected in [(20, set()), (21, {"A"}), (27, {"A"}), (28, set())]:
            with self.subTest(day=day):
                self.assertEqual(active_service_ids(date(2026, 9, day), [calendar("A")], []), expected)

    def test_single_day_range(self):
        day = date(2026, 9, 21)
        self.assertEqual(active_service_ids(day, [calendar("A", end_date=day)], []), {"A"})

    def test_empty_calendars_and_disabled_weekday(self):
        day = date(2026, 9, 21)
        self.assertEqual(active_service_ids(day, [], []), set())
        self.assertEqual(active_service_ids(day, [calendar("A", monday=0)], []), set())

    def test_matching_exceptions_add_and_remove_services(self):
        day = date(2026, 9, 21)
        rows = [calendar("KEEP"), calendar("REMOVE"), calendar("DISABLED", monday=0),
                calendar("OUTSIDE", start_date=date(2026, 9, 22))]
        exceptions = [
            {"service_id": service, "date": day, "exception_type": kind}
            for service, kind in [("REMOVE", 2), ("MISSING", 2), ("KEEP", 1),
                                  ("EXTRA", 1), ("DISABLED", 1), ("OUTSIDE", 1)]
        ]
        self.assertEqual(active_service_ids(day, rows, exceptions), {"KEEP", "EXTRA", "DISABLED", "OUTSIDE"})

    def test_exception_only_service(self):
        day = date(2026, 9, 21)
        self.assertEqual(active_service_ids(day, [], [
            {"service_id": "EXTRA", "date": day, "exception_type": 1},
        ]), {"EXTRA"})

    def test_exceptions_on_other_dates_have_no_effect(self):
        day = date(2026, 9, 21)
        exceptions = [
            {"service_id": service, "date": day + timedelta(days=offset), "exception_type": kind}
            for offset in (-1, 1) for service, kind in [("A", 2), ("EXTRA", 1)]
        ]
        self.assertEqual(active_service_ids(day, [calendar("A")], exceptions), {"A"})

    def test_does_not_mutate_inputs_or_retain_state_between_dates(self):
        rows = [calendar("A")]
        exceptions = [{"service_id": "A", "date": date(2026, 9, 21), "exception_type": 2}]
        original = deepcopy((rows, exceptions))
        for day, expected in [(21, set()), (22, {"A"}), (21, set())]:
            self.assertEqual(active_service_ids(date(2026, 9, day), rows, exceptions), expected)
        self.assertEqual((rows, exceptions), original)


if __name__ == "__main__":
    unittest.main()
