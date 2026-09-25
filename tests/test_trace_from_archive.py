"""Archive wrapper checks; main is mocked so no archived CSV is loaded."""

from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth import trace_schedule


class TraceFromArchiveTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("archive-fixture")
        self.day = date(2026, 9, 22)
        self.trip = "000123"
        self.receipt = datetime(2026, 9, 20, 12, 34, 56, 123456, tzinfo=timezone.utc)
        self.selected = {
            "zip_sha256": "b" * 64, "downloaded_at_utc": self.receipt,
            "feed_start_date": date(2026, 9, 1), "feed_end_date": date(2026, 9, 30),
        }

    def test_selected_hash_path_arguments_and_receipt_are_forwarded_and_reported(self):
        rows = [self.selected]
        output = StringIO()
        with patch.object(trace_schedule, "select_schedule_snapshot", return_value={
            "status": "selected", "snapshot": self.selected,
        }) as selector, patch.object(trace_schedule, "main") as main, redirect_stdout(output):
            trace_schedule.trace_from_archive(self.root, self.day, self.trip, rows, "America/New_York")
        selector.assert_called_once_with(self.day, rows, "America/New_York")
        main.assert_called_once_with(self.root / self.selected["zip_sha256"], self.day, self.trip)
        text = output.getvalue()
        self.assertIn(str(self.root / self.selected["zip_sha256"]), text)
        self.assertIn(self.selected["zip_sha256"], text)
        self.assertIn(str(self.receipt), text)
        self.assertIn("utc", text.lower())

    def test_unresolved_reports_outcome_without_calling_main(self):
        output = StringIO()
        with patch.object(trace_schedule, "select_schedule_snapshot", return_value={
            "status": "unresolved", "reason": "no eligible snapshot",
        }) as selector, patch.object(trace_schedule, "main") as main, redirect_stdout(output):
            trace_schedule.trace_from_archive(self.root, self.day, self.trip, [], "America/New_York")
        selector.assert_called_once_with(self.day, [], "America/New_York")
        main.assert_not_called()
        self.assertIn("no eligible snapshots", output.getvalue().lower())
        self.assertNotIn("selected path", output.getvalue().lower())

    def test_real_selector_routes_newest_eligible_snapshot_to_main(self):
        older = dict(self.selected, zip_sha256="a" * 64,
                     downloaded_at_utc=datetime(2026, 9, 10, tzinfo=timezone.utc))
        late = dict(self.selected, zip_sha256="c" * 64,
                    downloaded_at_utc=datetime(2026, 9, 22, 4, 0, 0, 1, tzinfo=timezone.utc))
        output = StringIO()
        with patch.object(trace_schedule, "main") as main, redirect_stdout(output):
            trace_schedule.trace_from_archive(self.root, self.day, self.trip,
                                              [late, older, self.selected], "America/New_York")
        main.assert_called_once_with(self.root / self.selected["zip_sha256"], self.day, self.trip)
        self.assertIn(str(self.receipt), output.getvalue())


if __name__ == "__main__":
    unittest.main()
