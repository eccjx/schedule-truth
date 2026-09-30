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
from schedule_truth.archive_schedule import archive_schedule_zip, load_schedule_snapshots, extract_schedule_zip
from schedule_truth.select_schedule_snapshot import select_schedule_snapshot


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

    def test_load_restores_one_typed_snapshot_per_receipt(self):
        first = archive_schedule_zip(self.source, self.archive, self.received)
        later = self.received + timedelta(microseconds=1)
        second = archive_schedule_zip(self.source, self.archive, later)
        snapshots = load_schedule_snapshots(self.archive)
        self.assertEqual(len(snapshots), 2)
        by_receipt = {}
        for snapshot in snapshots:
            by_receipt[snapshot['receipt_id']] = snapshot
            self.assertEqual(snapshot['zip_sha256'], first['content']['zip_sha256'])
            self.assertEqual(snapshot['zip_path'], first['content']['zip_path'])
            self.assertIs(type(snapshot['feed_start_date']), date)
            self.assertIs(type(snapshot['feed_end_date']), date)
            self.assertEqual(snapshot['feed_start_date'], date(2026, 9, 1))
            self.assertEqual(snapshot['feed_end_date'], date(2026, 9, 30))
            self.assertEqual(snapshot['agency_timezone_source'], 'agency.txt')
            self.assertEqual(snapshot['downloaded_at_utc'].utcoffset(), timedelta(0))
        self.assertEqual(by_receipt[first['receipt']['receipt_id']]['downloaded_at_utc'], self.received)
        self.assertEqual(by_receipt[second['receipt']['receipt_id']]['downloaded_at_utc'], later)
        self.assertIsNot(snapshots[0], snapshots[1])
        selected = select_schedule_snapshot(date(2026, 9, 22), snapshots, 'America/New_York')
        self.assertEqual(selected['snapshot']['receipt_id'], second['receipt']['receipt_id'])

    def test_load_preserves_unknown_coverage_and_fallback_evidence(self):
        source = write_zip(self.root / 'unknown.zip', feed=None, agency=None)
        saved = archive_schedule_zip(source, self.archive, self.received)
        snapshots = load_schedule_snapshots(self.archive)
        self.assertEqual(len(snapshots), 1)
        self.assertIsNone(snapshots[0]['feed_start_date'])
        self.assertIsNone(snapshots[0]['feed_end_date'])
        self.assertEqual(snapshots[0]['coverage_error'], saved['content']['coverage_error'])
        self.assertEqual(snapshots[0]['agency_timezone_error'], saved['content']['agency_timezone_error'])
        self.assertEqual(snapshots[0]['agency_timezone_source'], 'configured_fallback')
        self.assertEqual(select_schedule_snapshot(date(2026, 9, 22), snapshots, 'America/New_York')['status'], 'unresolved')

    def test_load_surfaces_missing_content_and_hash_mismatch(self):
        saved = archive_schedule_zip(self.source, self.archive, self.received)
        path = saved['content']['zip_path'].parent / 'content.json'
        content = json.loads(path.read_text(encoding='utf-8'))
        content['zip_sha256'] = 'different-hash'
        path.write_text(json.dumps(content), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'hash does not match receipt'):
            load_schedule_snapshots(self.archive)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            load_schedule_snapshots(self.archive)

    def test_load_does_not_invent_timezone_for_invalid_receipts(self):
        saved = archive_schedule_zip(self.source, self.archive, self.received)
        path = self.archive / 'receipts' / (saved['receipt']['receipt_id'] + '.json')
        receipt = json.loads(path.read_text(encoding='utf-8'))
        for value in ('2026-09-20T12:34:56.123456', '2026-09-20T12:34:56.123456-04:00', 'not-a-date'):
            with self.subTest(value=value):
                receipt['downloaded_at_utc'] = value
                path.write_text(json.dumps(receipt), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_schedule_snapshots(self.archive)

    def test_extract_keeps_zip_and_existing_files_and_adds_missing_files(self):
        saved = archive_schedule_zip(self.source, self.archive, self.received)
        digest = saved['content']['zip_sha256']
        zip_path = saved['content']['zip_path']
        original = zip_path.read_bytes()
        feed = extract_schedule_zip(self.archive, digest)
        self.assertEqual(feed, self.archive / digest / 'feed')
        self.assertEqual((feed / 'feed_info.txt').read_text(), VALID_FEED)
        existing = feed / 'marker.txt'
        existing.write_text('keep existing extraction', encoding='utf-8')
        os.utime(existing, (946684800, 946684800))
        state = (existing.read_bytes(), existing.stat().st_mtime_ns)
        (feed / 'agency.txt').unlink()
        self.assertEqual(extract_schedule_zip(self.archive, digest), feed)
        self.assertEqual((existing.read_bytes(), existing.stat().st_mtime_ns), state)
        self.assertEqual((feed / 'agency.txt').read_text(), VALID_AGENCY)
        self.assertEqual(zip_path.read_bytes(), original)

    def test_extract_does_not_write_outside_feed(self):
        saved = archive_schedule_zip(self.source, self.archive, self.received)
        with zipfile.ZipFile(saved['content']['zip_path'], 'a') as archive:
            archive.writestr('../outside.txt', 'must not escape')
        with self.assertRaisesRegex(ValueError, 'outside feed directory'):
            extract_schedule_zip(self.archive, saved['content']['zip_sha256'])
        self.assertFalse((saved['content']['zip_path'].parent / 'outside.txt').exists())

    def test_single_agency_timezone_fallback_preserves_zip_and_receipt(self):
        cases = {
            "missing_file": None,
            "empty_file": "",
            "header_only": "agency_id,agency_name,agency_timezone\n",
            "missing_column": "agency_id,agency_name\n1,MBTA\n",
            "blank_value": "agency_id,agency_name,agency_timezone\n1,MBTA,\n",
            "invalid_name": "agency_id,agency_name,agency_timezone\n1,MBTA,America/New_Yrok\n",
        }
        for label, agency in cases.items():
            with self.subTest(case=label):
                source = write_zip(self.root / (label + ".zip"), agency=agency)
                before = source.read_bytes()
                target = self.root / (label + "-archive")
                result = archive_schedule_zip(source, target, self.received)
                self.assert_persisted(result, source, self.received, target)
                saved = json.loads((result["content"]["zip_path"].parent / "content.json").read_text(encoding="utf-8"))
                for content in (result["content"], saved):
                    self.assertEqual(content["agency_timezone"], "America/New_York")
                    self.assertEqual(content["agency_timezone_source"], "configured_fallback")
                    self.assertIsInstance(content["agency_timezone_error"], str)
                    self.assertTrue(content["agency_timezone_error"].strip())
                    self.assertNotIn("coverage_error", content)
                self.assertEqual(result["content"]["feed_start_date"], date(2026, 9, 1))
                self.assertEqual(result["content"]["feed_end_date"], date(2026, 9, 30))
                self.assertEqual(source.read_bytes(), before)
                self.assertEqual(len(list((target / "receipts").glob("*.json"))), 1)

    def test_valid_single_agency_timezone_records_file_source_without_error(self):
        result = archive_schedule_zip(self.source, self.archive, self.received)
        self.assert_persisted(result, self.source, self.received)
        saved = json.loads((result["content"]["zip_path"].parent / "content.json").read_text(encoding="utf-8"))
        for content in (result["content"], saved):
            self.assertEqual(content["agency_timezone"], "America/New_York")
            self.assertEqual(content["agency_timezone_source"], "agency.txt")
            self.assertIsNone(content["agency_timezone_error"])

    def test_multiple_agencies_select_mbta_row_after_different_valid_timezone(self):
        agency = (
            "agency_id,agency_name,agency_timezone\n"
            "OTHER,Other Transit,America/Chicago\n"
            "MBTA,MBTA,America/New_York\n"
        )
        source = write_zip(self.root / "multiple-agencies.zip", agency=agency)
        before = source.read_bytes()
        result = archive_schedule_zip(source, self.archive, self.received)
        self.assert_persisted(result, source, self.received)
        persisted = json.loads((result["content"]["zip_path"].parent / "content.json").read_text(encoding="utf-8"))
        for content in (result["content"], persisted):
            self.assertEqual(content["agency_timezone"], "America/New_York")
            self.assertEqual(content["agency_timezone_source"], "agency.txt")
            self.assertIsNone(content["agency_timezone_error"])
        loaded = load_schedule_snapshots(self.archive)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["agency_timezone"], "America/New_York")
        self.assertEqual(source.read_bytes(), before)

    def test_missing_mbta_row_uses_fallback_and_reports_absent_row(self):
        agency = (
            "agency_id,agency_name,agency_timezone\n"
            "OTHER,Other Transit,America/Chicago\n"
            "SECOND,Second Transit,America/Los_Angeles\n"
        )
        source = write_zip(self.root / "no-mbta.zip", agency=agency)
        before = source.read_bytes()
        result = archive_schedule_zip(source, self.archive, self.received)
        self.assert_persisted(result, source, self.received)
        persisted = json.loads((result["content"]["zip_path"].parent / "content.json").read_text(encoding="utf-8"))
        for content in (result["content"], persisted):
            self.assertEqual(content["agency_timezone"], "America/New_York")
            self.assertEqual(content["agency_timezone_source"], "configured_fallback")
            reason = content["agency_timezone_error"]
            self.assertIsInstance(reason, str)
            self.assertIn("MBTA", reason)
            self.assertRegex(reason.lower(), r"missing|absent|not found")
            self.assertNotIn("blank", reason.lower())
        loaded = load_schedule_snapshots(self.archive)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["agency_timezone_source"], "configured_fallback")
        self.assertEqual(source.read_bytes(), before)

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
