"""Independent collector evidence checks using mocked HTTP and real archive files."""

from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth import collect_static_feed, trace_schedule
from schedule_truth.archive_schedule import load_schedule_snapshots


URL = "https://example.test/static.zip"
SERVICE_DATE = date(2099, 9, 22)


def schedule_zip(agency_timezone="America/New_York"):
    buffer = BytesIO()
    rows = {
        "agency.txt": f"agency_name,agency_timezone\nMBTA,{agency_timezone}\n",
        "feed_info.txt": "feed_start_date,feed_end_date\n20990101,20991231\n",
        "calendar.txt": (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "W,1,1,1,1,1,1,1,20990101,20991231\n"
        ),
        "calendar_dates.txt": "service_id,date,exception_type\n",
        "trips.txt": "trip_id,route_id,service_id\nT,R,W\n",
        "stop_times.txt": (
            "trip_id,stop_id,stop_sequence,arrival_time,departure_time\n"
            "T,START,1,10:00:00,10:01:00\n"
        ),
    }
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in rows.items():
            archive.writestr(name, body)
    return buffer.getvalue()


class IndependentCollectorTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "archive"
        self.connection = Mock()
        connection_patch = patch.object(
            collect_static_feed, "HTTPSConnection", return_value=self.connection
        )
        connection_patch.start()
        self.addCleanup(connection_patch.stop)

    def respond(self, body, status=200):
        response = Mock(status=status, reason="fixture status")
        response.read.side_effect = BytesIO(body).read
        self.connection.getresponse.return_value = response

    def saved_attempt(self, result):
        path = self.root / "attempts" / f"{result['attempt_id']}.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved, result)
        self.assertEqual(saved["request_url"], URL)
        self.assertEqual(datetime.fromisoformat(saved["attempted_at_utc"]).utcoffset(), timedelta(0))
        self.assertEqual(datetime.fromisoformat(saved["finished_at_utc"]).utcoffset(), timedelta(0))
        self.assertLessEqual(saved["attempted_at_utc"], saved["finished_at_utc"])
        return saved

    def assert_not_selectable(self):
        self.assertEqual(load_schedule_snapshots(self.root), [])
        self.assertEqual(list(self.root.glob("receipts/*.json")), [])
        self.assertEqual(list(self.root.glob("*/content.json")), [])
        output = StringIO()
        with redirect_stdout(output):
            trace_schedule.trace_from_archive(
                self.root, SERVICE_DATE, "T", "America/New_York"
            )
        self.assertIn("no eligible snapshots", output.getvalue().lower())
        self.assertEqual(list(self.root.glob("*/feed")), [])

    def test_no_byte_failure_has_attempt_only_and_retry_gets_new_identity(self):
        self.connection.request.side_effect = TimeoutError("offline")
        first = collect_static_feed.collect_static_feed(URL, self.root)
        second = collect_static_feed.collect_static_feed(URL, self.root)
        self.assertEqual(self.connection.request.call_count, 2)
        self.assertNotEqual(first["attempt_id"], second["attempt_id"])
        self.assertEqual(len(list(self.root.glob("attempts/*.json"))), 2)
        for result in (first, second):
            self.saved_attempt(result)
            self.assertEqual(result["outcome"], "failed")
            self.assertIn("offline", result["error"])
            self.assertNotIn("zip_sha256", result)
            self.assertNotIn("receipt_id", result)
        self.assert_not_selectable()

    def test_invalid_zip_bytes_are_retained_by_hash_but_never_selected(self):
        body = b"not-a-zip\x00\xff"
        self.respond(body)
        result = collect_static_feed.collect_static_feed(URL, self.root)
        self.saved_attempt(result)
        self.assertEqual(result["outcome"], "invalid_zip")
        self.assertEqual(result["zip_sha256"], sha256(body).hexdigest())
        self.assertEqual(
            Path(result["zip_path"]), self.root / result["zip_sha256"] / "original.zip"
        )
        self.assertEqual(Path(result["zip_path"]).read_bytes(), body)
        self.assertTrue(result["error"])
        self.assertNotIn("receipt_id", result)
        self.assert_not_selectable()

    def test_readable_http_error_is_unselectable_then_success_links_receipt(self):
        body = schedule_zip()
        self.respond(body, status=503)
        failed = collect_static_feed.collect_static_feed(URL, self.root)
        self.saved_attempt(failed)
        self.assertEqual(failed["outcome"], "failed")
        self.assertEqual(failed["http_status"], 503)
        self.assertIn("HTTP 503", failed["error"])
        self.assertEqual(failed["zip_sha256"], sha256(body).hexdigest())
        self.assertEqual(Path(failed["zip_path"]).read_bytes(), body)
        self.assertNotIn("receipt_id", failed)
        self.assert_not_selectable()

        self.respond(body, status=200)
        successful = collect_static_feed.collect_static_feed(URL, self.root)
        self.saved_attempt(successful)
        self.saved_attempt(failed)
        self.assertEqual(successful["outcome"], "archived")
        self.assertNotEqual(successful["attempt_id"], failed["attempt_id"])
        self.assertEqual(successful["zip_sha256"], failed["zip_sha256"])
        self.assertEqual(len(list(self.root.glob("attempts/*.json"))), 2)
        self.assertEqual(len(list(self.root.glob("receipts/*.json"))), 1)
        self.assertEqual(Path(successful["zip_path"]).read_bytes(), body)
        snapshots = load_schedule_snapshots(self.root)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["receipt_id"], successful["receipt_id"])
        self.assertEqual(snapshots[0]["zip_sha256"], successful["zip_sha256"])
        self.assertEqual(
            snapshots[0]["downloaded_at_utc"].isoformat(), successful["downloaded_at_utc"]
        )
        output = StringIO()
        with redirect_stdout(output):
            trace_schedule.trace_from_archive(
                self.root, SERVICE_DATE, "T", "America/New_York"
            )
        self.assertIn(successful["zip_sha256"], output.getvalue())
        self.assertIn("starting at stop START", output.getvalue())

    def test_caller_timezone_mismatch_rejected_before_archive_loading(self):
        self.respond(schedule_zip())
        successful = collect_static_feed.collect_static_feed(URL, self.root)
        self.assertEqual(successful["outcome"], "archived")
        with patch.object(trace_schedule, "load_schedule_snapshots") as loader, patch.object(
            trace_schedule, "extract_schedule_zip"
        ) as extractor:
            with self.assertRaisesRegex(ValueError, "MBTA traces require"):
                trace_schedule.trace_from_archive(
                    self.root, SERVICE_DATE, "T", "America/Chicago"
                )
        loader.assert_not_called()
        extractor.assert_not_called()

    def test_selected_archive_timezone_mismatch_rejected_without_extraction(self):
        self.respond(schedule_zip("America/Chicago"))
        successful = collect_static_feed.collect_static_feed(URL, self.root)
        self.assertEqual(successful["outcome"], "archived")
        self.assertEqual(load_schedule_snapshots(self.root)[0]["agency_timezone"], "America/Chicago")
        with patch.object(trace_schedule, "extract_schedule_zip") as extractor:
            with self.assertRaisesRegex(ValueError, "Selected archive timezone"):
                trace_schedule.trace_from_archive(
                    self.root, SERVICE_DATE, "T", "America/New_York"
                )
        extractor.assert_not_called()
        self.assertFalse((self.root / successful["zip_sha256"] / "feed").exists())


if __name__ == "__main__":
    unittest.main()
