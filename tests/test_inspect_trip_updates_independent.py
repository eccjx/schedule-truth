"""Independent, read-only checks for archived Trip Updates inspection."""

from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from google.transit import gtfs_realtime_pb2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth.inspect_trip_updates import inspect_trip_stop


REPO = Path(__file__).resolve().parents[1]
LIVE_ROOT = REPO / "data" / "raw" / "trip-updates-tester-20261005"
LIVE_REQUEST = "12ad66de9aaa422f96a4654a97cf3c53"
BOAT_TRIP = "Boat-F1-1930-Rowes-F1-D-PM-Weekday-Summer-26"


def feed_with_one_stop():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1791400001
    entity = feed.entity.add()
    entity.id = "entity-A"
    update = entity.trip_update
    update.trip.trip_id = "trip-A"
    update.trip.start_date = "20261102"
    update.timestamp = 1791399997
    stop = update.stop_time_update.add()
    stop.stop_sequence = 3
    stop.stop_id = "stop-3"
    stop.arrival.time = 1791400100
    stop.departure.time = 1791400150
    return feed


class InspectTripUpdatesTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "archive"
        self.request_id = "request-A"
        self.receipt = "2026-11-02T18:00:03.123456+00:00"

    def snapshot(self, root=None):
        root = self.root if root is None else root
        return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in root.rglob("*") if path.is_file()}

    def install(self, body=None, record_updates=None, save_payload=True):
        body = feed_with_one_stop().SerializeToString() if body is None else body
        digest = sha256(body).hexdigest()
        record = {
            "request_id": self.request_id,
            "feed_type": "trip_updates",
            "received_at_utc": self.receipt,
            "payload_sha256": digest,
            "valid_snapshot": True,
            "outcome": "received",
        }
        if record_updates:
            record.update(record_updates)
        request_path = self.root / "requests" / f"{self.request_id}.json"
        request_path.parent.mkdir(parents=True, exist_ok=True)
        request_path.write_text(json.dumps(record), encoding="utf-8")
        payload_path = self.root / "payloads" / record["payload_sha256"] / "response.pb"
        if save_payload:
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            payload_path.write_bytes(body)
        return request_path, payload_path

    def assert_rejects_read_only(self, error, pattern, root=None, request_id=None,
                                 trip_id="trip-A", stop_sequence=3):
        root = self.root if root is None else root
        request_id = self.request_id if request_id is None else request_id
        before = self.snapshot(root)
        with self.assertRaisesRegex(error, pattern):
            inspect_trip_stop(root, request_id, trip_id, stop_sequence)
        self.assertEqual(self.snapshot(root), before)

    def test_exact_trip_and_stop_follow_hash_verified_payload(self):
        request_path, payload_path = self.install()
        before = self.snapshot()
        result = inspect_trip_stop(self.root, self.request_id, "trip-A", 3)
        self.assertEqual(result, {
            "request_id": self.request_id,
            "payload_sha256": sha256(payload_path.read_bytes()).hexdigest(),
            "trip_id": "trip-A",
            "trip_start_date": "20261102",
            "stop_sequence": 3,
            "stop_id": "stop-3",
            "arrival_time": 1791400100,
            "departure_time": 1791400150,
            "trip_update_timestamp": 1791399997,
            "feed_timestamp": 1791400001,
            "received_at_utc": self.receipt,
        })
        self.assertEqual(json.loads(request_path.read_text(encoding="utf-8"))["payload_sha256"],
                         result["payload_sha256"])
        self.assertEqual(self.snapshot(), before)

    def test_absent_optional_source_fields_return_none(self):
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.header.gtfs_realtime_version = "2.0"
        entity = feed.entity.add()
        entity.id = "missing-fields"
        entity.trip_update.trip.trip_id = "trip-A"
        entity.trip_update.stop_time_update.add().stop_sequence = 3
        self.install(feed.SerializeToString())
        before = self.snapshot()
        result = inspect_trip_stop(self.root, self.request_id, "trip-A", 3)
        for name in ("trip_start_date", "stop_id", "arrival_time", "departure_time",
                     "trip_update_timestamp", "feed_timestamp"):
            self.assertIsNone(result[name], name)
        self.assertEqual(result["received_at_utc"], self.receipt)
        self.assertEqual(self.snapshot(), before)

    def test_missing_trip_or_stop_is_not_misidentified(self):
        self.install()
        self.assert_rejects_read_only(LookupError, "not found", trip_id="different-trip")
        self.assert_rejects_read_only(LookupError, "not found", stop_sequence=99)

    def test_duplicate_trip_or_stop_match_is_ambiguous(self):
        for kind in ("two_entities", "two_stops"):
            with self.subTest(kind=kind):
                feed = feed_with_one_stop()
                if kind == "two_entities":
                    extra = feed.entity.add()
                    extra.CopyFrom(feed.entity[0])
                    extra.id = "entity-B"
                else:
                    extra_stop = feed.entity[0].trip_update.stop_time_update.add()
                    extra_stop.CopyFrom(feed.entity[0].trip_update.stop_time_update[0])
                    extra_stop.stop_id = "another-stop"
                self.install(feed.SerializeToString())
                self.assert_rejects_read_only(ValueError, "Ambiguous trip")

    def test_missing_wrong_feed_and_terminal_without_payload(self):
        self.assert_rejects_read_only(FileNotFoundError, "Request record not found")
        self.install(record_updates={"feed_type": "vehicle_positions"})
        self.assert_rejects_read_only(ValueError, "Not a Trip Updates request")
        request_path = self.root / "requests" / f"{self.request_id}.json"
        record = json.loads(request_path.read_text(encoding="utf-8"))
        record["feed_type"] = "trip_updates"
        record.pop("payload_sha256")
        record["valid_snapshot"] = False
        record["outcome"] = "interrupted"
        request_path.write_text(json.dumps(record), encoding="utf-8")
        self.assert_rejects_read_only(ValueError, "no complete payload")

    def test_invalid_snapshot_missing_payload_and_corrupt_hash(self):
        request_path, payload_path = self.install(record_updates={"valid_snapshot": False})
        self.assert_rejects_read_only(ValueError, "not a valid Trip Updates snapshot")
        record = json.loads(request_path.read_text(encoding="utf-8"))
        record["valid_snapshot"] = True
        request_path.write_text(json.dumps(record), encoding="utf-8")
        payload_path.unlink()
        self.assert_rejects_read_only(FileNotFoundError, "Payload not found")
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_bytes(b"tampered")
        self.assert_rejects_read_only(ValueError, "Payload hash mismatch")

    def test_hash_verified_but_invalid_protobuf_is_rejected(self):
        self.install(body=b"\xffnot protobuf")
        self.assert_rejects_read_only(ValueError, "Invalid Trip Updates payload")
        incomplete = gtfs_realtime_pb2.FeedMessage().SerializePartialToString()
        self.install(body=incomplete)
        self.assert_rejects_read_only(ValueError, "Incomplete Trip Updates payload")

    @unittest.skipUnless((LIVE_ROOT / "requests" / f"{LIVE_REQUEST}.json").is_file(),
                         "retained October 5 archive is unavailable")
    def test_retained_boat_request_has_arrival_and_missing_departure(self):
        before = self.snapshot(LIVE_ROOT)
        result = inspect_trip_stop(LIVE_ROOT, LIVE_REQUEST, BOAT_TRIP, 1)
        self.assertEqual(result["request_id"], LIVE_REQUEST)
        self.assertEqual(result["payload_sha256"],
                         "a7193b2de3125bbe5edb810aff55429b09e3555c009afbf265c7049cf128780f")
        self.assertEqual(result["trip_id"], BOAT_TRIP)
        self.assertEqual(result["stop_sequence"], 1)
        self.assertEqual(result["stop_id"], "Boat-Hingham")
        self.assertEqual(result["arrival_time"], 1791244733)
        self.assertIsNone(result["departure_time"])
        self.assertEqual(result["trip_update_timestamp"], 1791244487)
        self.assertEqual(result["feed_timestamp"], 1791244501)
        self.assertEqual(result["received_at_utc"], "2026-10-05T23:55:04.144893+00:00")
        self.assertEqual(self.snapshot(LIVE_ROOT), before)


if __name__ == "__main__":
    unittest.main()
