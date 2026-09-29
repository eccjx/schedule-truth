"""Archive contract checks using tiny deterministic ZIPs and isolated storage."""

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth.archive_schedule import archive_schedule_zip


VALID_FEED = "feed_start_date,feed_end_date\n20260901,20260930\n"
VALID_AGENCY = "agency_id,agency_name,agency_timezone\n1,MBTA,America/New_York\n"


def write_zip(path, feed=VALID_FEED, agency=VALID_AGENCY, marker="fixture"):
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in [("feed_info.txt", feed), ("agency.txt", agency), ("marker.txt", marker)]:
            if text is not None:
                archive.writestr(zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)), text.encode("utf-8"))
    return path


class ArchiveScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "archive"
        self.source = write_zip(self.root / "source.zip")
        self.received = datetime(2026, 9, 20, 12, 34, 56, 123456, tzinfo=timezone.utc)

    def assert_persisted(self, result, source, received, archive_root=None):
        archive_root = self.archive if archive_root is None else archive_root
        original = source.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        content = result["content"]
        receipt = result["receipt"]
        zip_path = archive_root / digest / "original.zip"
        self.assertEqual(content["zip_sha256"], digest)
        self.assertEqual(content["zip_path"], zip_path)
        self.assertEqual(zip_path.read_bytes(), original)
        persisted = json.loads((zip_path.parent / "content.json").read_text(encoding="utf-8"))
        expected = dict(content, zip_path=str(zip_path))
        for field in ("feed_start_date", "feed_end_date"):
            expected[field] = content[field].isoformat() if content[field] is not None else None
        self.assertEqual(persisted, expected)
        self.assertEqual(receipt["zip_sha256"], digest)
        self.assertEqual(receipt["downloaded_at_utc"], received)
        receipt_path = archive_root / "receipts" / (receipt["receipt_id"] + ".json")
        saved_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_receipt, dict(receipt, downloaded_at_utc=received.isoformat()))
        parsed = datetime.fromisoformat(saved_receipt["downloaded_at_utc"])
        self.assertEqual(parsed, received)
        self.assertEqual(parsed.utcoffset(), timedelta(0))
        self.assertEqual(parsed.microsecond, received.microsecond)

    def test_valid_content_and_receipt_json(self):
        before = self.source.read_bytes()
        result = archive_schedule_zip(self.source, self.archive, self.received)
        self.assertEqual(result["content"]["feed_start_date"], date(2026, 9, 1))
        self.assertEqual(result["content"]["feed_end_date"], date(2026, 9, 30))
        self.assertEqual(result["content"]["agency_timezone"], "America/New_York")
        self.assertNotIn("coverage_error", result["content"])
        self.assert_persisted(result, self.source, self.received)
        self.assertEqual(self.source.read_bytes(), before)

    def test_identical_bytes_preserve_content_and_retain_distinct_receipts(self):
        first = archive_schedule_zip(self.source, self.archive, self.received)
        zip_path = first["content"]["zip_path"]
        content_path = zip_path.parent / "content.json"
        receipt_path = self.archive / "receipts" / (first["receipt"]["receipt_id"] + ".json")
        # An old mtime detects rewrites even if serialized bytes stay identical.
        for path in (zip_path, content_path):
            os.utime(path, (946684800, 946684800))
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (zip_path, content_path, receipt_path)}
        copy = self.root / "second-download.zip"
        copy.write_bytes(self.source.read_bytes())
        later = self.received + timedelta(microseconds=1)
        second = archive_schedule_zip(copy, self.archive, later)
        self.assertEqual(first["content"], second["content"])
        self.assertNotEqual(first["receipt"]["receipt_id"], second["receipt"]["receipt_id"])
        self.assertEqual(len(list(self.archive.glob("*/content.json"))), 1)
        self.assertEqual(len(list(self.archive.glob("*/original.zip"))), 1)
        self.assertEqual(len(list((self.archive / "receipts").glob("*.json"))), 2)
        for path, state in before.items():
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), state)
        self.assert_persisted(first, self.source, self.received)
        self.assert_persisted(second, copy, later)

    def test_different_zip_bytes_get_different_hashes_and_paths(self):
        other = write_zip(self.root / "other.zip", marker="different bytes, same coverage")
        first = archive_schedule_zip(self.source, self.archive, self.received)
        second = archive_schedule_zip(other, self.archive, self.received)
        self.assertNotEqual(first["content"]["zip_sha256"], second["content"]["zip_sha256"])
        self.assertNotEqual(first["content"]["zip_path"], second["content"]["zip_path"])
        self.assertEqual(len(list(self.archive.glob("*/content.json"))), 2)
        self.assertEqual(len(list((self.archive / "receipts").glob("*.json"))), 2)
        self.assert_persisted(first, self.source, self.received)
        self.assert_persisted(second, other, self.received)

    def assert_unknown_coverage(self, feed, label):
        source = write_zip(self.root / "invalid-coverage.zip", feed=feed)
        target = self.root / label
        result = archive_schedule_zip(source, target, self.received)
        self.assert_persisted(result, source, self.received, target)
        self.assertIsNone(result["content"]["feed_start_date"])
        self.assertIsNone(result["content"]["feed_end_date"])
        self.assertTrue(result["content"].get("coverage_error"))

    def test_missing_empty_and_incomplete_feed_info_retains_evidence(self):
        cases = [None, "", "feed_start_date,feed_end_date\n",
                 "feed_end_date\n20260930\n", "feed_start_date\n20260901\n",
                 "feed_publisher_name\nMBTA\n", "feed_start_date,feed_end_date\n,20260930\n",
                 "feed_start_date,feed_end_date\n20260901,\n", "feed_start_date,feed_end_date\n,\n"]
        for index, feed in enumerate(cases):
            with self.subTest(feed=feed):
                self.assert_unknown_coverage(feed, "missing-" + str(index))

    def test_malformed_dates_retain_evidence_and_clear_both_dates(self):
        for index, value in enumerate(("garbage", "20260230", "2026-09-01", "20261301",
                                        "202609011", "2026091", "202691")):
            for field in ("start", "end"):
                with self.subTest(field=field, value=value):
                    start, end = (value, "20260930") if field == "start" else ("20260901", value)
                    self.assert_unknown_coverage(
                        "feed_start_date,feed_end_date\n" + start + "," + end + "\n",
                        "malformed-" + str(index) + field,
                    )

    def test_reversed_coverage_retains_evidence(self):
        self.assert_unknown_coverage("feed_start_date,feed_end_date\n20260930,20260901\n", "reversed")

    def test_aware_utc_receipts_are_accepted(self):
        for stamp in (self.received, self.received.replace(tzinfo=timezone(timedelta(0), "UTC"))):
            with self.subTest(stamp=stamp):
                self.assert_persisted(archive_schedule_zip(self.source, self.archive, stamp), self.source, stamp)

    def test_naive_and_nonzero_offset_receipts_are_rejected_before_writes(self):
        for stamp in (self.received.replace(tzinfo=None),
                      self.received.replace(tzinfo=timezone(timedelta(hours=-4))),
                      self.received.replace(tzinfo=timezone(timedelta(hours=1)))):
            with self.subTest(stamp=stamp):
                with self.assertRaises(ValueError):
                    archive_schedule_zip(self.source, self.archive, stamp)
                self.assertFalse(self.archive.exists())


if __name__ == "__main__":
    unittest.main()
