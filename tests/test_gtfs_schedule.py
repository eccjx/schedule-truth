"""Public schedule integration checks with normalized rows and no mocked helpers.

These characterize existing behavior, not an accepted CSV/duplicate/type contract.
"""

from copy import deepcopy
from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth.gtfs_schedule import scheduled_stop_times_for_date


class ScheduledStopTimesForDateTests(unittest.TestCase):
    def setUp(self):
        self.day = date(2026, 9, 21)
        self.calendars = [{
            "service_id": "WK", "start_date": self.day, "end_date": date(2026, 9, 27),
            "monday": 1, "tuesday": 1, "wednesday": 1, "thursday": 1,
            "friday": 1, "saturday": 0, "sunday": 0,
        }]
        self.trips = [
            {"trip_id": "A", "service_id": "WK"},
            {"trip_id": "EMPTY", "service_id": "WK"},
            {"trip_id": "B", "service_id": "EX"},
        ]
        self.stops = [
            {"trip_id": "A", "stop_sequence": 10, "arrival_time": "25:10:00"},
            {"trip_id": "B", "stop_sequence": 1, "arrival_time": "08:00:00"},
            {"trip_id": "A", "stop_sequence": 2, "arrival_time": "24:00:00"},
            {"trip_id": "ORPHAN", "stop_sequence": 1, "arrival_time": "09:00:00"},
        ]

    def test_ordinary_service_filters_trips_and_orders_stops(self):
        self.assertEqual(
            scheduled_stop_times_for_date(self.day, self.calendars, [], self.trips, self.stops),
            {"A": [self.stops[2], self.stops[0]], "EMPTY": []},
        )

    def test_exceptions_replace_regular_service(self):
        exceptions = [
            {"service_id": "WK", "date": self.day, "exception_type": 2},
            {"service_id": "EX", "date": self.day, "exception_type": 1},
        ]
        self.assertEqual(
            scheduled_stop_times_for_date(self.day, self.calendars, exceptions, self.trips, self.stops),
            {"B": [self.stops[1]]},
        )

    def test_exception_only_schedule(self):
        exceptions = [{"service_id": "EX", "date": self.day, "exception_type": 1}]
        self.assertEqual(
            scheduled_stop_times_for_date(self.day, [], exceptions, self.trips, self.stops),
            {"B": [self.stops[1]]},
        )

    def test_no_active_service(self):
        for day in [date(2026, 9, 20), date(2026, 9, 26), date(2026, 9, 28)]:
            with self.subTest(day=day):
                self.assertEqual(scheduled_stop_times_for_date(day, self.calendars, [], self.trips, self.stops), {})

    def test_empty_inputs_and_missing_stops(self):
        self.assertEqual(scheduled_stop_times_for_date(self.day, [], [], [], []), {})
        self.assertEqual(scheduled_stop_times_for_date(self.day, self.calendars, [], [], self.stops), {})
        self.assertEqual(
            scheduled_stop_times_for_date(self.day, self.calendars, [], self.trips, []),
            {"A": [], "EMPTY": []},
        )

    def test_repeated_calls_do_not_mutate_inputs_or_accumulate_stops(self):
        exceptions = [{"service_id": "EX", "date": date(2026, 9, 22), "exception_type": 1}]
        original = deepcopy((self.calendars, exceptions, self.trips, self.stops))
        expected = {"A": [deepcopy(self.stops[2]), deepcopy(self.stops[0])], "EMPTY": []}
        for _ in range(2):
            self.assertEqual(
                scheduled_stop_times_for_date(self.day, self.calendars, exceptions, self.trips, self.stops),
                expected,
            )
        self.assertEqual((self.calendars, exceptions, self.trips, self.stops), original)


if __name__ == "__main__":
    unittest.main()
