"""Independent persisted-archive checks with small, distinct schedule ZIPs."""

from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth.archive_schedule import (
    archive_schedule_zip, extract_schedule_zip, load_schedule_snapshots,
)
from schedule_truth.trace_schedule import trace_from_archive


DAY = date(2026, 9, 22)
CUTOFF = datetime(2026, 9, 22, 4, tzinfo=timezone.utc)
TRIP = "T-1"


def make_zip(path, first_stop):
    files = {
        "feed_info.txt": "feed_start_date,feed_end_date\n20260901,20260930\n",
        "agency.txt": "agency_id,agency_timezone\nMBTA,America/New_York\n",
        "calendar.txt": (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "W,1,1,1,1,1,0,0,20260901,20260930\n"
        ),
        "calendar_dates.txt": "service_id,date,exception_type\n",
        "trips.txt": "route_id,service_id,trip_id\nR,W,T-1\n",
        "stop_times.txt": (
            "trip_id,stop_id,stop_sequence,arrival_time,departure_time\n"
            f"T-1,END,10,25:10:00,25:11:00\nT-1,{first_stop},2,24:00:00,24:01:00\n"
        ),
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return path


class PersistedArchiveIndependentTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.archive = self.root / "archive"

    def archive_one(self, name, first_stop, received):
        source = make_zip(self.root / name, first_stop)
        result = archive_schedule_zip(source, self.archive, received)
        original = source.read_bytes()
        source.unlink()
        self.assertEqual(result["content"]["zip_sha256"], sha256(original).hexdigest())
        self.assertEqual(result["content"]["zip_path"].read_bytes(), original)
        return result

    def trace(self):
        output = StringIO()
        with redirect_stdout(output):
            trace_from_archive(self.archive, DAY, TRIP, "America/New_York")
        return output.getvalue()

    def test_deleted_downloads_select_latest_receipt_and_trace_its_content(self):
        a = self.archive_one("old.zip", "OLD", CUTOFF - timedelta(days=2))
        b = self.archive_one("new.zip", "NEW", CUTOFF - timedelta(microseconds=1))
        latest = self.archive_one("repeat.zip", "NEW", CUTOFF)
        too_late = self.archive_one("late.zip", "LATE", CUTOFF + timedelta(microseconds=1))
        self.assertEqual(b["content"]["zip_sha256"], latest["content"]["zip_sha256"])
        self.assertNotEqual(b["receipt"]["receipt_id"], latest["receipt"]["receipt_id"])
        self.assertEqual(len(list(self.archive.glob("*/original.zip"))), 3)
        snapshots = load_schedule_snapshots(self.archive)
        self.assertEqual(len(snapshots), 4)
        self.assertEqual({s["receipt_id"] for s in snapshots}, {
            a["receipt"]["receipt_id"], b["receipt"]["receipt_id"],
            latest["receipt"]["receipt_id"], too_late["receipt"]["receipt_id"],
        })
        for snapshot in snapshots:
            self.assertEqual(snapshot["zip_path"].read_bytes(),
                             (self.archive / snapshot["zip_sha256"] / "original.zip").read_bytes())
            self.assertEqual(snapshot["feed_start_date"], date(2026, 9, 1))
            self.assertEqual(snapshot["feed_end_date"], date(2026, 9, 30))

        first = self.trace()
        second = self.trace()
        self.assertEqual(first, second)
        self.assertIn(str(self.archive / latest["content"]["zip_sha256"] / "feed"), first)
        self.assertIn(str(CUTOFF) + " utc", first)
        self.assertIn("starting at stop NEW at 24:01:00", first)
        self.assertIn("ending at stop END at 25:10:00", first)
        self.assertNotIn("stop OLD", first)
        self.assertNotIn("stop LATE", first)
        selected_feed = self.archive / latest["content"]["zip_sha256"] / "feed"
        self.assertIn("T-1,NEW,2,24:00:00,24:01:00", (selected_feed / "stop_times.txt").read_text())
        self.assertFalse((self.archive / a["content"]["zip_sha256"] / "feed").exists())
        self.assertFalse((self.archive / too_late["content"]["zip_sha256"] / "feed").exists())

    def test_unresolved_from_persisted_receipt_after_cutoff_does_not_extract(self):
        saved = self.archive_one("late.zip", "LATE", CUTOFF + timedelta(microseconds=1))
        output = self.trace()
        self.assertIn("no eligible snapshots", output.lower())
        self.assertNotIn("starting at stop", output)
        self.assertFalse((self.archive / saved["content"]["zip_sha256"] / "feed").exists())

    def test_malformed_receipt_and_mismatched_content_metadata_surface(self):
        saved = self.archive_one("valid.zip", "GOOD", CUTOFF)
        receipt_path = self.archive / "receipts" / (saved["receipt"]["receipt_id"] + ".json")
        content_path = saved["content"]["zip_path"].parent / "content.json"
        original_receipt = receipt_path.read_text(encoding="utf-8")
        original_content = content_path.read_text(encoding="utf-8")
        for replacement in ("not-a-timestamp", "2026-09-22T04:00:00", "2026-09-22T04:00:00-04:00"):
            with self.subTest(receipt=replacement):
                receipt = json.loads(original_receipt)
                receipt["downloaded_at_utc"] = replacement
                receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_schedule_snapshots(self.archive)
                receipt_path.write_text(original_receipt, encoding="utf-8")
        for field, value in (("zip_sha256", "f" * 64), ("feed_start_date", "not-a-date")):
            with self.subTest(field=field):
                content = json.loads(original_content)
                content[field] = value
                content_path.write_text(json.dumps(content), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_schedule_snapshots(self.archive)
                content_path.write_text(original_content, encoding="utf-8")
        self.assertFalse((content_path.parent / "feed").exists())

    def test_mismatched_retained_zip_cannot_be_traced_under_old_hash(self):
        original = self.archive_one("original.zip", "ORIGINAL", CUTOFF)
        replacement = make_zip(self.root / "replacement.zip", "REPLACED").read_bytes()
        expected_hash = original["content"]["zip_sha256"]
        self.assertNotEqual(sha256(replacement).hexdigest(), expected_hash)
        original["content"]["zip_path"].write_bytes(replacement)
        # A trace may reject a mismatch or identify the actual bytes; this test
        # does not prescribe recovery. It must not claim the old hash for them.
        try:
            output = self.trace()
        except (ValueError, OSError):
            self.assertFalse((self.archive / expected_hash / "feed").exists())
        else:
            actual_hash = sha256(replacement).hexdigest()
            self.assertIn(actual_hash, output)
            self.assertNotIn(expected_hash, output)


if __name__ == "__main__":
    unittest.main()
