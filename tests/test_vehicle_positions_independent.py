"""Independent persistence checks for the first Vehicle Positions slice."""

from datetime import datetime, timedelta
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from google.transit import gtfs_realtime_pb2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth import collect_vehicle_positions as collector


def complete_feed():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1790876142
    first = feed.entity.add()
    first.id = "vehicle-a"
    first.vehicle.vehicle.id = "A"
    first.vehicle.timestamp = 1790876101
    second = feed.entity.add()
    second.id = "vehicle-b"
    second.vehicle.vehicle.id = "B"
    return feed.SerializeToString()


class IndependentVehiclePositionsTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "vehicle-positions"
        self.url = "https://example.test/realtime/VehiclePositions.pb"
        self.connection = Mock()
        connection_patch = patch.object(collector, "HTTPSConnection", return_value=self.connection)
        connection_patch.start()
        self.addCleanup(connection_patch.stop)

    def respond(self, body, status=200):
        response = Mock(status=status, reason="fixture status")
        response.getheader.return_value = str(len(body))
        response.read.side_effect = BytesIO(body).read
        self.connection.getresponse.return_value = response

    def poll(self):
        return collector.collect_vehicle_positions(self.url, self.root, 0, 1)[0]

    def persisted(self, record):
        path = self.root / "requests" / (record["request_id"] + ".json")
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved, record)
        self.assertEqual(saved["request_url"], self.url)
        self.assertEqual(datetime.fromisoformat(saved["request_started_at_utc"]).utcoffset(), timedelta(0))
        self.assertEqual(datetime.fromisoformat(saved["finished_at_utc"]).utcoffset(), timedelta(0))
        self.assertNotEqual(saved["outcome"], "started")
        return path

    def assert_payload(self, record, body):
        digest = sha256(body).hexdigest()
        self.assertEqual(record["payload_sha256"], digest)
        self.assertEqual(Path(record["payload_path"]), self.root / "payloads" / digest / "response.pb")
        self.assertEqual(Path(record["payload_path"]).read_bytes(), body)
        self.assertEqual(record["size_bytes"], len(body))
        self.assertEqual(datetime.fromisoformat(record["received_at_utc"]).utcoffset(), timedelta(0))

    def test_duplicate_complete_responses_keep_one_payload_and_two_unchanged_records(self):
        body = complete_feed()
        self.respond(body)
        first = self.poll()
        first_path = self.persisted(first)
        self.assert_payload(first, body)
        before = (first_path.read_bytes(), Path(first["payload_path"]).read_bytes())
        self.respond(body)
        second = self.poll()
        self.persisted(second)
        self.assert_payload(second, body)
        self.assertNotEqual(first["request_id"], second["request_id"])
        self.assertEqual(len(list((self.root / "requests").glob("*.json"))), 2)
        self.assertEqual(len(list(self.root.glob("payloads/*/response.pb"))), 1)
        self.assertEqual((first_path.read_bytes(), Path(first["payload_path"]).read_bytes()), before)
        for record in (first, second):
            self.assertEqual(record["outcome"], "received")
            self.assertTrue(record["valid_snapshot"])
            self.assertEqual(record["feed_timestamp"], 1790876142)
            self.assertEqual(record["vehicle_timestamps"], [
                {"entity_id": "vehicle-a", "vehicle_timestamp": 1790876101},
                {"entity_id": "vehicle-b", "vehicle_timestamp": None},
            ])

    def test_no_byte_timeout_persists_error_without_payload(self):
        self.connection.request.side_effect = TimeoutError("no bytes")
        record = self.poll()
        path = self.persisted(record)
        self.assertEqual(record["outcome"], "failed")
        self.assertFalse(record["valid_snapshot"])
        self.assertIn("no bytes", record["error"])
        self.assertNotIn("payload_sha256", record)
        self.assertNotIn("received_at_utc", record)
        self.assertFalse(path.with_suffix(".part").exists())
        self.assertEqual(list(self.root.glob("payloads/*/response.pb")), [])

    def test_complete_malformed_protobuf_retains_bytes_but_not_valid_snapshot(self):
        body = b"\xffinvalid protobuf"
        self.respond(body)
        record = self.poll()
        self.persisted(record)
        self.assert_payload(record, body)
        self.assertEqual(record["http_status"], 200)
        self.assertEqual(record["outcome"], "failed")
        self.assertFalse(record["valid_snapshot"])
        self.assertIn("DecodeError", record["error"])
        self.assertNotIn("feed_timestamp", record)

    def test_http_error_with_readable_protobuf_remains_failed(self):
        body = complete_feed()
        self.respond(body, 503)
        record = self.poll()
        self.persisted(record)
        self.assert_payload(record, body)
        self.assertEqual(record["http_status"], 503)
        self.assertEqual(record["outcome"], "failed")
        self.assertFalse(record["valid_snapshot"])
        self.assertIn("HTTP 503", record["error"])
        self.assertNotIn("feed_timestamp", record)

    def test_restart_records_partial_size_then_removes_part_and_uses_new_id(self):
        requests = self.root / "requests"
        requests.mkdir(parents=True)
        old = requests / "prior.json"
        original = {
            "request_id": "prior", "request_url": self.url,
            "request_started_at_utc": "2026-10-01T10:00:00+00:00",
            "outcome": "started", "valid_snapshot": False,
        }
        old.write_text(json.dumps(original), encoding="utf-8")
        partial = old.with_suffix(".part")
        partial.write_bytes(b"unfinished bytes")
        self.respond(complete_feed())
        current = self.poll()
        recovered = json.loads(old.read_text(encoding="utf-8"))
        self.persisted(current)
        self.assertEqual(recovered["request_id"], original["request_id"])
        self.assertEqual(recovered["request_started_at_utc"], original["request_started_at_utc"])
        self.assertEqual(recovered["outcome"], "interrupted")
        self.assertEqual(recovered["response_outcome"], "unknown")
        self.assertTrue(recovered["partial_staging_existed"])
        self.assertEqual(recovered["partial_staging_size_bytes"], len(b"unfinished bytes"))
        self.assertEqual(datetime.fromisoformat(recovered["interrupted_at_utc"]).utcoffset(), timedelta(0))
        self.assertNotIn("payload_sha256", recovered)
        self.assertFalse(partial.exists())
        self.assertNotEqual(current["request_id"], "prior")
        before = old.read_bytes()
        collector.collect_vehicle_positions(self.url, self.root, 0, 0)
        self.assertEqual(old.read_bytes(), before)
        self.assertEqual(len(list(self.root.glob("payloads/*/response.pb"))), 1)


if __name__ == "__main__":
    unittest.main()
