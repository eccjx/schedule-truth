"""Regression checks for trip helpers using normalized, integer stop sequences.

Run from the repository root:
    python -B -m unittest discover -s tests -p test_gtfs_trips.py -v

These characterize the current valid-input behavior; they do not establish
contracts for malformed rows, duplicate identifiers/sequences, or CSV coercion.
"""

from copy import deepcopy
from pathlib import Path
import sys
import unittest


# The repository has a src layout but no installed package configuration yet.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth.gtfs_trips import group_trip_stop_times, select_active_trips


class SelectActiveTripsTests(unittest.TestCase):
    def test_filters_by_service_id_and_preserves_input_order_and_fields(self):
        rows = [
            {"trip_id": "T3", "service_id": "WK", "route_id": "R2"},
            {"trip_id": "T1", "service_id": "WE", "route_id": "R1"},
            {"trip_id": "T2", "service_id": "WK", "route_id": "R1"},
            {"trip_id": "T4", "service_id": "EX", "route_id": "R3"},
        ]
        self.assertEqual(
            select_active_trips(rows, {"WK", "EX", "UNKNOWN"}),
            [rows[0], rows[2], rows[3]],
        )

    def test_empty_and_nonmatching_inputs(self):
        rows = [{"trip_id": "WK", "service_id": "WE"}]
        for trips, services in [([], {"WK"}), (rows, set()), (rows, {"WK"})]:
            with self.subTest(trips=trips, services=services):
                self.assertEqual(select_active_trips(trips, services), [])

    def test_does_not_modify_inputs(self):
        rows = [
            {"trip_id": "T2", "service_id": "WE"},
            {"trip_id": "T1", "service_id": "WK"},
        ]
        services = {"WK"}
        original = deepcopy((rows, services))
        select_active_trips(rows, services)
        self.assertEqual((rows, services), original)


class GroupTripStopTimesTests(unittest.TestCase):
    def test_groups_interleaved_rows_and_sorts_numeric_sequences(self):
        trips = [{"trip_id": "A"}, {"trip_id": "B"}]
        rows = [
            {"trip_id": "A", "stop_id": "S10", "stop_sequence": 10},
            {"trip_id": "B", "stop_id": "SB2", "stop_sequence": 2},
            {"trip_id": "A", "stop_id": "S2", "stop_sequence": 2},
            {"trip_id": "OTHER", "stop_id": "SX", "stop_sequence": 1},
            {"trip_id": "B", "stop_id": "SB1", "stop_sequence": 1},
            {"trip_id": "A", "stop_id": "S1", "stop_sequence": 1},
        ]
        self.assertEqual(
            group_trip_stop_times(trips, rows),
            {"A": [rows[5], rows[2], rows[0]], "B": [rows[4], rows[1]]},
        )

    def test_selected_trip_without_stop_times_has_empty_group(self):
        row = {"trip_id": "A", "stop_sequence": 1}
        self.assertEqual(
            group_trip_stop_times([{"trip_id": "A"}, {"trip_id": "B"}], [row]),
            {"A": [row], "B": []},
        )

    def test_empty_inputs(self):
        row = {"trip_id": "A", "stop_sequence": 1}
        for trips, rows, expected in [
            ([], [], {}),
            ([], [row], {}),
            ([{"trip_id": "A"}], [], {"A": []}),
        ]:
            with self.subTest(trips=trips, rows=rows):
                self.assertEqual(group_trip_stop_times(trips, rows), expected)

    def test_repeated_stop_visits_and_extended_hour_fields_are_preserved(self):
        rows = [
            {"trip_id": "A", "stop_id": "S", "stop_sequence": 3,
             "arrival_time": "25:10:00", "departure_time": "25:11:00"},
            {"trip_id": "A", "stop_id": "S", "stop_sequence": 1,
             "arrival_time": "23:59:00", "departure_time": "24:00:00"},
        ]
        self.assertEqual(
            group_trip_stop_times([{"trip_id": "A"}], rows),
            {"A": [rows[1], rows[0]]},
        )

    def test_does_not_modify_inputs_and_repeated_calls_do_not_accumulate(self):
        trips = [{"trip_id": "A"}]
        rows = [
            {"trip_id": "A", "stop_sequence": 10},
            {"trip_id": "A", "stop_sequence": 2},
        ]
        original = deepcopy((trips, rows))
        expected = {"A": [deepcopy(rows[1]), deepcopy(rows[0])]}
        first = group_trip_stop_times(trips, rows)
        self.assertEqual(first, expected)
        self.assertEqual(group_trip_stop_times(trips, rows), expected)
        self.assertEqual((trips, rows), original)
        first["A"].clear()
        self.assertEqual(group_trip_stop_times(trips, rows), expected)
        self.assertEqual((trips, rows), original)

    def test_selection_and_grouping_exclude_inactive_trips(self):
        trips = [
            {"trip_id": "A", "service_id": "WK"},
            {"trip_id": "B", "service_id": "WE"},
        ]
        rows = [
            {"trip_id": "B", "stop_sequence": 1},
            {"trip_id": "A", "stop_sequence": 1},
        ]
        self.assertEqual(
            group_trip_stop_times(select_active_trips(trips, {"WK"}), rows),
            {"A": [rows[1]]},
        )


if __name__ == "__main__":
    unittest.main()
