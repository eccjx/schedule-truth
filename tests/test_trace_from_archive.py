"""Archive wrapper routing and a persisted archive-to-trace integration."""

from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
import sys
import unittest
from tempfile import TemporaryDirectory
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth import trace_schedule
from schedule_truth.archive_schedule import archive_schedule_zip


class TraceFromArchiveTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("archive-fixture")
        self.day = date(2026, 9, 22)
        self.trip = "000123"
        self.receipt = datetime(2026, 9, 20, 12, 34, 56, 123456, tzinfo=timezone.utc)
        self.selected = {
            "zip_sha256": "b" * 64, "downloaded_at_utc": self.receipt,
            "feed_start_date": date(2026, 9, 1), "feed_end_date": date(2026, 9, 30),
            "agency_timezone": "America/New_York",
        }
        self.loader = patch.object(trace_schedule, "load_schedule_snapshots", return_value=[self.selected]).start()
        self.extractor = patch.object(
            trace_schedule, "extract_schedule_zip",
            side_effect=lambda root, digest: root / digest / "feed",
        ).start()
        self.addCleanup(patch.stopall)

    def test_selected_hash_path_arguments_and_receipt_are_forwarded_and_reported(self):
        rows = [self.selected]
        output = StringIO()
        with patch.object(trace_schedule, "select_schedule_snapshot", return_value={
            "status": "selected", "snapshot": self.selected,
        }) as selector, patch.object(trace_schedule, "main") as main, redirect_stdout(output):
            trace_schedule.trace_from_archive(self.root, self.day, self.trip, "America/New_York")
        self.loader.assert_called_once_with(self.root)
        self.extractor.assert_called_once_with(self.root, self.selected["zip_sha256"])
        selector.assert_called_once_with(self.day, rows, "America/New_York")
        main.assert_called_once_with(self.root / self.selected["zip_sha256"] / "feed", self.day, self.trip)
        text = output.getvalue()
        self.assertIn(str(self.root / self.selected["zip_sha256"]), text)
        self.assertIn(self.selected["zip_sha256"], text)
        self.assertIn(str(self.receipt), text)
        self.assertIn("utc", text.lower())

    def test_unresolved_reports_outcome_without_calling_main(self):
        self.loader.return_value = []
        output = StringIO()
        with patch.object(trace_schedule, "select_schedule_snapshot", return_value={
            "status": "unresolved", "reason": "no eligible snapshot",
        }) as selector, patch.object(trace_schedule, "main") as main, redirect_stdout(output):
            trace_schedule.trace_from_archive(self.root, self.day, self.trip, "America/New_York")
        selector.assert_called_once_with(self.day, [], "America/New_York")
        main.assert_not_called()
        self.extractor.assert_not_called()
        self.assertIn("no eligible snapshots", output.getvalue().lower())
        self.assertNotIn("selected path", output.getvalue().lower())

    def test_wrong_caller_timezone_is_rejected_before_loading(self):
        with self.assertRaisesRegex(ValueError, "MBTA traces require"):
            trace_schedule.trace_from_archive(self.root, self.day, self.trip, "America/Los_Angeles")
        self.loader.assert_not_called()
        self.extractor.assert_not_called()

    def test_selected_archive_timezone_mismatch_is_rejected_before_extraction(self):
        mismatched = dict(self.selected, agency_timezone="America/Chicago")
        with patch.object(trace_schedule, "select_schedule_snapshot", return_value={
            "status": "selected", "snapshot": mismatched,
        }), patch.object(trace_schedule, "main") as main:
            with self.assertRaisesRegex(ValueError, "Selected archive timezone"):
                trace_schedule.trace_from_archive(self.root, self.day, self.trip, "America/New_York")
        self.extractor.assert_not_called()
        main.assert_not_called()

    def test_real_selector_routes_newest_eligible_snapshot_to_main(self):
        older = dict(self.selected, zip_sha256="a" * 64,
                     downloaded_at_utc=datetime(2026, 9, 10, tzinfo=timezone.utc))
        late = dict(self.selected, zip_sha256="c" * 64,
                    downloaded_at_utc=datetime(2026, 9, 22, 4, 0, 0, 1, tzinfo=timezone.utc))
        output = StringIO()
        self.loader.return_value = [late, older, self.selected]
        with patch.object(trace_schedule, "main") as main, redirect_stdout(output):
            trace_schedule.trace_from_archive(self.root, self.day, self.trip, "America/New_York")
        main.assert_called_once_with(self.root / self.selected["zip_sha256"] / "feed", self.day, self.trip)
        self.assertIn(str(self.receipt), output.getvalue())


class PersistedArchiveTraceTests(unittest.TestCase):
    def test_trace_uses_disk_receipts_and_extracts_only_selected_content(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.zip"
            archive_root = root / "archive"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("feed_info.txt", "feed_start_date,feed_end_date\n20260901,20260930\n")
                archive.writestr("agency.txt", "agency_timezone\nAmerica/New_York\n")
                archive.writestr("calendar.txt", "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n001,1,1,1,1,1,0,0,20260901,20260930\n")
                archive.writestr("calendar_dates.txt", "service_id,date,exception_type\n")
                archive.writestr("trips.txt", "trip_id,route_id,service_id\n000123,01,001\n")
                archive.writestr("stop_times.txt", "trip_id,stop_id,stop_sequence,arrival_time,departure_time\n000123,LAST,10,25:10:00,25:11:00\n000123,FIRST,2,24:00:00,24:01:00\n")
            archive_schedule_zip(source, archive_root, datetime(2026, 9, 20, tzinfo=timezone.utc))
            cutoff = datetime(2026, 9, 22, 4, 0, 0, tzinfo=timezone.utc)
            archive_schedule_zip(source, archive_root, cutoff)
            archive_schedule_zip(source, archive_root, cutoff.replace(microsecond=1))
            digest = next(archive_root.glob("*/content.json")).parent.name
            source.unlink()
            for _ in range(2):
                output = StringIO()
                with redirect_stdout(output):
                    trace_schedule.trace_from_archive(archive_root, date(2026, 9, 22), "000123", "America/New_York")
                self.assertIn(str(archive_root / digest / "feed"), output.getvalue())
                self.assertIn(str(cutoff) + " utc", output.getvalue())
                self.assertIn("2 visits, starting at stop FIRST at 24:01:00 and ending at stop LAST at 25:10:00", output.getvalue())


if __name__ == "__main__":
    unittest.main()
