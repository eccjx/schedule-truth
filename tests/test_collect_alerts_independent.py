"""Independent persistence checks for complete Service Alerts responses."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from google.transit import gtfs_realtime_pb2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth.collect_alerts import persist_alerts_response


def alerts_bytes(with_timestamp=True):
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    if with_timestamp:
        feed.header.timestamp = 1793659351
    entity = feed.entity.add()
    entity.id = "alert-1001875"
    first = entity.alert.active_period.add()
    first.start = 1793660400
    first.end = 1793692800
    second = entity.alert.active_period.add()
    second.start = 1793700000
    return feed.SerializeToString()


class AlertsPersistenceTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "alerts"
        self.started = datetime(2026, 11, 2, 22, 43, 0, tzinfo=timezone.utc)
        self.received = self.started + timedelta(seconds=2, microseconds=345678)
        self.body = alerts_bytes()

    def persist(self, request_id="first", body=None, status=200,
                started=None, received=None):
        return persist_alerts_response(
            self.root, request_id, self.body if body is None else body,
            status, self.started if started is None else started,
            self.received if received is None else received)

    def saved(self, record):
        path = self.root / "requests" / f"{record['request_id']}.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), record)
        return path

    def files(self):
        return {str(path.relative_to(self.root)): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()}

    def test_identical_bytes_share_payload_but_not_request_or_receipt(self):
        first = self.persist()
        first_path = self.saved(first)
        payload = Path(first["payload_path"])
        os.utime(first_path, (946684800, 946684800))
        os.utime(payload, (946684800, 946684800))
        earlier = self.files()
        second = self.persist("second", started=self.started + timedelta(seconds=60),
                              received=self.received + timedelta(seconds=60))
        self.saved(second)
        self.assertEqual(first["feed_type"], second["feed_type"])
        self.assertEqual(first["feed_type"], "service_alerts")
        self.assertNotEqual(first["request_id"], second["request_id"])
        self.assertNotEqual(first["request_started_at_utc"], second["request_started_at_utc"])
        self.assertNotEqual(first["received_at_utc"], second["received_at_utc"])
        self.assertEqual(first["payload_sha256"], sha256(self.body).hexdigest())
        self.assertEqual(second["payload_sha256"], first["payload_sha256"])
        self.assertEqual(Path(second["payload_path"]), payload)
        self.assertEqual(payload.read_bytes(), self.body)
        self.assertEqual(len(list(self.root.glob("payloads/*/response.pb"))), 1)
        for relative, evidence in earlier.items():
            path = self.root / relative
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), evidence)

        self.assertEqual(first["request_started_at_utc"], self.started.isoformat())
        self.assertEqual(first["received_at_utc"], self.received.isoformat())
        self.assertEqual(datetime.fromisoformat(first["finished_at_utc"]).utcoffset(), timedelta(0))
        self.assertEqual(first["feed_timestamp"], 1793659351)
        self.assertNotEqual(first["feed_timestamp"], int(self.received.timestamp()))
        for record in (first, second):
            self.assertEqual(record["outcome"], "received")
            self.assertTrue(record["valid_snapshot"])
            self.assertFalse(any(isinstance(value, (list, dict)) for value in record.values()))
            for field in ("active_period", "active_periods", "alert", "alerts", "period_start", "period_end"):
                self.assertNotIn(field, record)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(payload.read_bytes())
        periods = feed.entity[0].alert.active_period
        self.assertEqual([(period.start, period.end if period.HasField("end") else None)
                          for period in periods], [(1793660400, 1793692800), (1793700000, None)])

    def test_exact_replay_and_conflicts_leave_every_file_unchanged(self):
        original = self.persist()
        request = self.saved(original)
        payload = Path(original["payload_path"])
        for path in (request, payload):
            os.utime(path, (946684800, 946684800))
        before = self.files()
        self.assertEqual(self.persist(), original)
        self.assertEqual(self.files(), before)
        variants = (
            {"body": self.body + b"\x00"},
            {"status": 503},
            {"started": self.started + timedelta(microseconds=1)},
            {"received": self.received + timedelta(microseconds=1)},
        )
        for kwargs in variants:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "Conflicting"):
                self.persist(**kwargs)
            self.assertEqual(self.files(), before)

    def test_terminal_no_payload_ids_cannot_be_completed(self):
        request_dir = self.root / "requests"
        request_dir.mkdir(parents=True)
        for request_id, outcome in (("timed-out", "failed"), ("interrupted", "interrupted")):
            path = request_dir / f"{request_id}.json"
            path.write_text(json.dumps({
                "request_id": request_id, "feed_type": "service_alerts",
                "request_started_at_utc": self.started.isoformat(),
                "outcome": outcome, "valid_snapshot": False,
            }), encoding="utf-8")
            before = self.files()
            with self.subTest(outcome=outcome), self.assertRaisesRegex(ValueError, "Terminal request without payload"):
                self.persist(request_id)
            self.assertEqual(self.files(), before)
        self.assertEqual(list(self.root.glob("payloads/*/response.pb")), [])

    def test_malformed_and_http_error_bodies_are_exact_failed_evidence(self):
        malformed = self.persist("malformed", body=b"\xffbad wire")
        http_error = self.persist("http-error", status=503)
        for record, body in ((malformed, b"\xffbad wire"), (http_error, self.body)):
            self.saved(record)
            self.assertEqual(record["outcome"], "failed")
            self.assertFalse(record["valid_snapshot"])
            self.assertTrue(record["error"])
            self.assertNotIn("active_period", record)
            self.assertNotIn("alerts", record)
            self.assertEqual(Path(record["payload_path"]).read_bytes(), body)
            self.assertEqual(record["payload_sha256"], sha256(body).hexdigest())
            self.assertEqual(record["size_bytes"], len(body))
        self.assertIn("DecodeError", malformed["error"])
        self.assertIn("HTTP 503", http_error["error"])
        self.assertEqual(len(list(self.root.glob("payloads/*/response.pb"))), 2)
        before = self.files()
        self.assertEqual(self.persist("malformed", body=b"\xffbad wire"), malformed)
        self.assertEqual(self.persist("http-error", status=503), http_error)
        self.assertEqual(self.files(), before)

    def test_missing_or_corrupt_saved_payload_is_not_repaired_or_relinked(self):
        record = self.persist()
        request = self.saved(record)
        payload = Path(record["payload_path"])
        payload.write_bytes(b"tampered")
        before = self.files()
        for request_id in ("first", "new"):
            with self.subTest(request_id=request_id), self.assertRaisesRegex(ValueError, "integrity mismatch"):
                self.persist(request_id)
            self.assertEqual(self.files(), before)
        payload.unlink()
        before = self.files()
        with self.assertRaisesRegex(ValueError, "Missing terminal payload"):
            self.persist()
        self.assertEqual(self.files(), before)
        self.assertEqual(json.loads(request.read_text(encoding="utf-8")), record)

    def test_absent_feed_timestamp_and_non_utc_collection_times(self):
        record = self.persist(body=alerts_bytes(with_timestamp=False))
        self.assertIsNone(record["feed_timestamp"])
        before = self.files()
        for bad_time in (datetime(2026, 11, 2, 22, 43),
                         datetime(2026, 11, 2, 17, 43, tzinfo=timezone(timedelta(hours=-5)))):
            with self.subTest(bad_time=bad_time):
                with self.assertRaisesRegex(ValueError, "aware UTC"):
                    self.persist("bad", started=bad_time)
                with self.assertRaisesRegex(ValueError, "aware UTC"):
                    self.persist("bad", received=bad_time)
                self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
