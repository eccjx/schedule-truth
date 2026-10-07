"""Independent checks of compact request metadata and retained Trip Updates bytes."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from google.transit import gtfs_realtime_pb2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth import collect_trip_updates as collector


def source_feed():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1791400000
    first = feed.entity.add()
    first.id = "update-A"
    first.trip_update.trip.trip_id = "000123"
    first.trip_update.trip.start_date = "20261007"
    first.trip_update.timestamp = 1791399900
    stop = first.trip_update.stop_time_update.add()
    stop.stop_id = "42"
    stop.stop_sequence = 2
    stop.arrival.time = 1791399800
    stop.departure.time = 1791400200
    second = feed.entity.add()
    second.id = "update-B"
    second.trip_update.trip.trip_id = "000124"
    second.trip_update.stop_time_update.add().stop_id = "43"
    return feed.SerializeToString()


class CompactTripUpdatesTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "archive"
        self.started = datetime(2026, 10, 7, 17, 0, tzinfo=timezone.utc)
        self.received = self.started + timedelta(seconds=4)
        self.body = source_feed()

    def persist(self, request_id="first", body=None, status=200,
                started=None, received=None):
        return collector.persist_trip_updates_response(
            self.root, request_id, self.body if body is None else body, status,
            self.started if started is None else started,
            self.received if received is None else received)

    def files(self):
        return {str(path.relative_to(self.root)): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()}

    def test_new_request_is_scalar_and_linked_bytes_recover_source_fields(self):
        result = self.persist()
        request = self.root / "requests" / "first.json"
        saved = json.loads(request.read_text(encoding="utf-8"))
        self.assertEqual(saved, result)
        self.assertFalse(any(isinstance(value, (list, dict)) for value in saved.values()))
        for name in ("trip_updates", "stop_time_updates", "entities",
                     "trip_update_timestamp", "arrival_time", "departure_time"):
            self.assertNotIn(name, saved)
        self.assertEqual(saved["feed_type"], "trip_updates")
        self.assertEqual(saved["request_started_at_utc"], self.started.isoformat())
        self.assertEqual(saved["received_at_utc"], self.received.isoformat())
        self.assertEqual(saved["feed_timestamp"], 1791400000)
        self.assertEqual(datetime.fromisoformat(saved["finished_at_utc"]).utcoffset(), timedelta(0))
        self.assertEqual(saved["outcome"], "received")
        self.assertTrue(saved["valid_snapshot"])

        digest = sha256(self.body).hexdigest()
        payload = self.root / "payloads" / digest / "response.pb"
        self.assertEqual(saved["payload_sha256"], digest)
        self.assertEqual(Path(saved["payload_path"]), payload)
        self.assertEqual(saved["size_bytes"], len(self.body))
        self.assertEqual(payload.read_bytes(), self.body)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(payload.read_bytes())
        self.assertTrue(feed.IsInitialized())
        self.assertEqual(feed.header.timestamp, saved["feed_timestamp"])
        first = feed.entity[0].trip_update
        self.assertEqual(feed.entity[0].id, "update-A")
        self.assertEqual(first.trip.trip_id, "000123")
        self.assertEqual(first.trip.start_date, "20261007")
        self.assertEqual(first.timestamp, 1791399900)
        self.assertEqual(first.stop_time_update[0].stop_id, "42")
        self.assertEqual(first.stop_time_update[0].stop_sequence, 2)
        self.assertEqual(first.stop_time_update[0].arrival.time, 1791399800)
        self.assertEqual(first.stop_time_update[0].departure.time, 1791400200)
        self.assertFalse(feed.entity[1].trip_update.HasField("timestamp"))
        self.assertFalse(feed.entity[1].trip_update.stop_time_update[0].HasField("arrival"))
        self.assertFalse(feed.entity[1].trip_update.stop_time_update[0].HasField("departure"))

    def test_expanded_historical_replay_keeps_json_and_payload_bytes(self):
        compact = self.persist()
        request = self.root / "requests" / "first.json"
        historical = compact.copy()
        historical["trip_updates"] = [{
            "entity_id": "update-A", "trip_id": "000123",
            "trip_update_timestamp": 1791399900,
            "stop_time_updates": [{"stop_id": "42", "arrival_time": 1791399800,
                                   "departure_time": 1791400200}],
        }]
        request.write_bytes(json.dumps(historical, indent=2).encode("utf-8") + b"\r\n")
        os.utime(request, (946684800, 946684800))
        payload = Path(compact["payload_path"])
        os.utime(payload, (946684800, 946684800))
        before = self.files()
        self.assertEqual(self.persist(), historical)
        self.assertEqual(self.files(), before)
        for kwargs in ({"body": self.body + b"\x00"}, {"status": 503},
                       {"started": self.started + timedelta(microseconds=1)},
                       {"received": self.received + timedelta(microseconds=1)}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "Conflicting"):
                self.persist(**kwargs)
            self.assertEqual(self.files(), before)

    def test_failure_and_payload_link_rules_survive_compaction(self):
        bad = self.persist("malformed", body=b"\xffnot protobuf")
        http = self.persist("http-error", status=503)
        for record, body in ((bad, b"\xffnot protobuf"), (http, self.body)):
            saved = json.loads((self.root / "requests" / f"{record['request_id']}.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, record)
            self.assertEqual(saved["outcome"], "failed")
            self.assertFalse(saved["valid_snapshot"])
            self.assertNotIn("trip_updates", saved)
            self.assertEqual(Path(saved["payload_path"]).read_bytes(), body)
            self.assertEqual(saved["payload_sha256"], sha256(body).hexdigest())
        self.assertIn("DecodeError", bad["error"])
        self.assertIn("HTTP 503", http["error"])
        self.assertEqual(len(list(self.root.glob("payloads/*/response.pb"))), 2)

        def incomplete(url, staging, timeout, limit, deadline):
            staging.write_bytes(b"partial")
            return {"complete": False, "request_error": "Incomplete response"}

        with patch.object(collector, "_receive_with_deadline", incomplete):
            partial = collector.poll_trip_updates("https://example.test/TripUpdates.pb", self.root)
        self.assertEqual(partial["outcome"], "failed")
        self.assertNotIn("payload_sha256", partial)
        self.assertEqual(partial["partial_staging_size_bytes"], 7)
        self.assertFalse((self.root / "requests" / f"{partial['request_id']}.part").exists())
        before = self.files()
        with self.assertRaisesRegex(ValueError, "Terminal request without payload"):
            self.persist(partial["request_id"],
                         started=datetime.fromisoformat(partial["request_started_at_utc"]))
        self.assertEqual(self.files(), before)
        linked = Path(http["payload_path"])
        linked.write_bytes(b"tampered")
        before = self.files()
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            self.persist("new")
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
