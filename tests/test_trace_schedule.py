"""Run the trace entry point against isolated files, with real loaders/helpers."""

from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from gtfs_fixture import write_feed, write_table


SOURCE = Path(__file__).resolve().parents[1] / "src"


class TraceScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.feed = self.root / "data" / "raw" / "MBTA_GTFS"
        write_feed(self.feed)

    def run_trace(self):
        return subprocess.run(
            [sys.executable, "-B", "-c",
             "import runpy, sys; sys.path.insert(0, sys.argv[1]); "
             "runpy.run_module('schedule_truth.trace_schedule', run_name='__main__')", str(SOURCE)],
            cwd=self.root, capture_output=True, text=True, timeout=20,
        )

    def assert_trace_output(self, expected):
        before = {p.name: p.read_bytes() for p in self.feed.iterdir()}
        result = self.run_trace()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, expected + "\n")
        self.assertEqual({p.name: p.read_bytes() for p in self.feed.iterdir()}, before)

    def test_trace_sorts_numerically_and_uses_departure_then_arrival(self):
        self.assert_trace_output(
            "Trip 78942566 has 2 visits, starting at stop FIRST at 24:00:00 "
            "and ending at stop LAST at 25:10:00."
        )

    def test_active_trip_with_no_stops_has_distinct_message(self):
        write_table(self.feed, "stop_times.txt", [])
        self.assert_trace_output("Trip 78942566 is scheduled, but no stop-time rows were found.")

    def test_removed_service_is_not_scheduled(self):
        write_table(self.feed, "calendar_dates.txt", [["001", "20260922", "2"]])
        self.assert_trace_output("The trip is not scheduled on this date.")

    def test_absent_trip_is_not_scheduled(self):
        write_table(self.feed, "trips.txt", [])
        self.assert_trace_output("The trip is not scheduled on this date.")

    def test_exception_only_service_and_single_stop(self):
        write_table(self.feed, "calendar.txt", [])
        write_table(self.feed, "calendar_dates.txt", [["001", "20260922", "1"]])
        write_table(self.feed, "stop_times.txt", [["78942566", "ONLY", "1", "09:00:00", "09:01:00"]])
        self.assert_trace_output(
            "Trip 78942566 has 1 visits, starting at stop ONLY at 09:01:00 "
            "and ending at stop ONLY at 09:00:00."
        )

    def test_missing_feed_file_fails_without_success_message(self):
        (self.feed / "trips.txt").unlink()
        result = self.run_trace()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("FileNotFoundError", result.stderr)

    def test_invalid_csv_value_fails_without_partial_trace(self):
        write_table(self.feed, "stop_times.txt", [["78942566", "ONLY", "bad", "09:00:00", "09:01:00"]])
        result = self.run_trace()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("ValueError", result.stderr)
        self.assertIn("stop_sequence", result.stderr)


if __name__ == "__main__":
    unittest.main()
