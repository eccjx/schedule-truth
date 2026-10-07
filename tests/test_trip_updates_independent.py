"""Independent Trip Updates checks of persisted evidence and runner behavior."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest

from google.transit import gtfs_realtime_pb2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth import collect_trip_updates as collector
from schedule_truth import run_trip_updates as runner


def update_bytes():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1791223190
    entity = feed.entity.add()
    entity.id = "trip-1"
    entity.trip_update.trip.trip_id = "000123"
    entity.trip_update.timestamp = 1791223180
    stop = entity.trip_update.stop_time_update.add()
    stop.stop_id = "42"
    stop.stop_sequence = 1
    stop.arrival.time = 1791219600
    stop.departure.time = 1791226800
    absent = feed.entity.add()
    absent.id = "trip-2"
    absent.trip_update.trip.trip_id = "000124"
    absent.trip_update.stop_time_update.add().stop_id = "43"
    return feed.SerializeToString()


class OnePoll:
    def is_set(self):
        return False

    def wait(self, seconds):
        return True


class TwoPolls:
    def __init__(self):
        self.waits = []

    def is_set(self):
        return False

    def wait(self, seconds):
        self.waits.append(seconds)
        time.sleep(seconds)
        return len(self.waits) == 2


@unittest.skipUnless(os.name == "nt", "Windows transport and ownership only")
class IndependentTripUpdatesTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "trip-updates"
        self.started = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
        self.received = self.started + timedelta(seconds=3)
        self.body = update_bytes()

    def persist(self, request_id, body=None, status=200, started=None, received=None):
        return collector.persist_trip_updates_response(
            self.root, request_id, self.body if body is None else body, status,
            self.started if started is None else started,
            self.received if received is None else received)

    def all_files(self):
        return {str(path.relative_to(self.root)): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()}

    def saved(self, record):
        path = self.root / "requests" / f"{record['request_id']}.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), record)
        return path

    def records(self):
        return [json.loads(path.read_text(encoding="utf-8"))
                for path in (self.root / "requests").glob("*.json")]

    def start_server(self, responses):
        pending = list(responses)
        seen = []
        release = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                seen.append(self.path)
                status, body, advertised = pending.pop(0)
                if status == "blocked":
                    release.wait(5)
                    return
                self.send_response(status)
                self.send_header("Content-Length", str(len(body) if advertised is None else advertised))
                self.end_headers()
                try:
                    self.wfile.write(body)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
                self.close_connection = True

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def close():
            release.set()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.addCleanup(close)
        return f"http://127.0.0.1:{server.server_port}/TripUpdates.pb", seen

    def test_duplicate_payload_exact_replay_and_distinct_source_times(self):
        one = self.persist("one")
        two = self.persist("two", received=self.received + timedelta(seconds=30))
        self.saved(one)
        self.saved(two)
        self.assertEqual(one["feed_type"], two["feed_type"])
        self.assertEqual(one["feed_type"], "trip_updates")
        self.assertNotEqual(one["request_id"], two["request_id"])
        self.assertNotEqual(one["received_at_utc"], two["received_at_utc"])
        self.assertEqual(one["payload_sha256"], sha256(self.body).hexdigest())
        self.assertEqual(one["payload_sha256"], two["payload_sha256"])
        self.assertEqual(Path(one["payload_path"]).read_bytes(), self.body)
        self.assertEqual(len(list(self.root.glob("payloads/*/response.pb"))), 1)
        self.assertEqual(one["request_started_at_utc"], self.started.isoformat())
        self.assertEqual(one["received_at_utc"], self.received.isoformat())
        self.assertEqual(datetime.fromisoformat(one["finished_at_utc"]).utcoffset(), timedelta(0))
        self.assertEqual(one["feed_timestamp"], 1791223190)
        self.assertNotIn("trip_updates", one)
        for value in one.values():
            self.assertNotIsInstance(value, (list, dict))
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(Path(one["payload_path"]).read_bytes())
        self.assertEqual(feed.entity[0].trip_update.timestamp, 1791223180)
        first_stop = feed.entity[0].trip_update.stop_time_update[0]
        self.assertEqual(first_stop.arrival.time, 1791219600)
        self.assertEqual(first_stop.departure.time, 1791226800)
        self.assertFalse(feed.entity[1].trip_update.HasField("timestamp"))
        self.assertFalse(feed.entity[1].trip_update.stop_time_update[0].HasField("arrival"))
        self.assertNotIn("actual", json.dumps(one))
        before = self.all_files()
        self.assertEqual(self.persist("one"), one)
        self.assertEqual(self.all_files(), before)

    def test_conflicts_and_terminal_ids_reject_before_any_write(self):
        self.persist("one")
        original = self.all_files()
        variants = [
            {"body": self.body + b"\x00"},
            {"status": 503},
            {"started": self.started + timedelta(microseconds=1)},
            {"received": self.received + timedelta(microseconds=1)},
        ]
        for kwargs in variants:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "Conflicting"):
                self.persist("one", **kwargs)
            self.assertEqual(self.all_files(), original)

        requests = self.root / "requests"
        for request_id, outcome in (("timeout", "failed"), ("restart", "interrupted")):
            (requests / f"{request_id}.json").write_text(json.dumps({
                "request_id": request_id, "feed_type": "trip_updates",
                "request_started_at_utc": self.started.isoformat(),
                "outcome": outcome, "valid_snapshot": False,
            }), encoding="utf-8")
            before = self.all_files()
            with self.subTest(outcome=outcome), self.assertRaisesRegex(ValueError, "Terminal request without payload"):
                self.persist(request_id)
            self.assertEqual(self.all_files(), before)

    def test_corrupt_and_missing_payload_never_repair_or_relink(self):
        record = self.persist("one")
        payload = Path(record["payload_path"])
        payload.write_bytes(b"tampered")
        before = self.all_files()
        for request_id in ("one", "new"):
            with self.subTest(request_id=request_id), self.assertRaisesRegex(ValueError, "integrity mismatch"):
                self.persist(request_id)
            self.assertEqual(self.all_files(), before)
        payload.unlink()
        before = self.all_files()
        with self.assertRaisesRegex(ValueError, "Missing terminal payload"):
            self.persist("one")
        self.assertEqual(self.all_files(), before)

    def test_http_malformed_and_incomplete_transfers_save_distinct_evidence(self):
        url, seen = self.start_server([
            (503, self.body, None),
            (200, b"\xffnot protobuf", None),
            (200, self.body[:12], len(self.body) + 50),
        ])
        records = [collector.poll_trip_updates(url, self.root, timeout=5,
                   request_deadline_seconds=5) for _ in range(3)]
        self.assertEqual(len(seen), 3)
        self.assertEqual(len({r["request_id"] for r in records}), 3)
        self.assertEqual(len(list(self.root.glob("requests/*.json"))), 3)
        for record in records:
            self.saved(record)
            self.assertEqual(record["feed_type"], "trip_updates")
            self.assertEqual(record["request_url"], url)
            self.assertEqual(record["outcome"], "failed")
            self.assertFalse(record["valid_snapshot"])
            self.assertFalse((self.root / "requests" / f"{record['request_id']}.part").exists())
        http_error, malformed, incomplete = records
        self.assertEqual(http_error["http_status"], 503)
        self.assertEqual(Path(http_error["payload_path"]).read_bytes(), self.body)
        self.assertEqual(http_error["payload_sha256"], sha256(self.body).hexdigest())
        self.assertIn("HTTP 503", http_error["error"])
        self.assertEqual(Path(malformed["payload_path"]).read_bytes(), b"\xffnot protobuf")
        self.assertIn("DecodeError", malformed["error"])
        self.assertNotIn("feed_timestamp", malformed)
        self.assertNotIn("payload_sha256", incomplete)
        self.assertNotIn("received_at_utc", incomplete)
        self.assertEqual(incomplete["partial_staging_size_bytes"], 12)
        self.assertEqual(len(list(self.root.glob("payloads/*/response.pb"))), 2)

    def test_restart_recovers_partial_then_polls_under_new_id(self):
        old_path = self.root / "requests" / "old.json"
        old_path.parent.mkdir(parents=True)
        old_path.write_text(json.dumps({"request_id": "old", "feed_type": "trip_updates",
                                        "request_started_at_utc": self.started.isoformat(),
                                        "outcome": "started", "valid_snapshot": False}), encoding="utf-8")
        old_path.with_suffix(".part").write_bytes(b"unfinished")
        url, seen = self.start_server([(200, self.body, None)])
        runner.run_trip_updates(url, self.root, interval_seconds=0, timeout=5,
                                request_deadline_seconds=5, stop_event=OnePoll())
        self.assertEqual(len(seen), 1)
        recovered = json.loads(old_path.read_text(encoding="utf-8"))
        self.assertEqual(recovered["outcome"], "interrupted")
        self.assertEqual(recovered["response_outcome"], "unknown")
        self.assertEqual(recovered["partial_staging_size_bytes"], len(b"unfinished"))
        self.assertFalse(old_path.with_suffix(".part").exists())
        fresh = next(r for r in (json.loads(p.read_text(encoding="utf-8"))
                 for p in (self.root / "requests").glob("*.json")) if r["request_id"] != "old")
        self.assertEqual(fresh["outcome"], "received")
        self.assertEqual(fresh["feed_type"], "trip_updates")
        self.assertEqual(Path(fresh["payload_path"]).read_bytes(), self.body)

    def test_runner_waits_after_failure_then_succeeds_without_overlap(self):
        url, seen = self.start_server([(503, self.body, None), (200, self.body, None)])
        stop = TwoPolls()
        runner.run_trip_updates(url, self.root, interval_seconds=0.08, timeout=5,
                                request_deadline_seconds=5, stop_event=stop)
        self.assertEqual(stop.waits, [0.08, 0.08])
        self.assertEqual(len(seen), 2)
        failed, received = sorted(self.records(), key=lambda row: row["request_started_at_utc"])
        self.assertEqual((failed["outcome"], received["outcome"]), ("failed", "received"))
        self.assertNotEqual(failed["request_id"], received["request_id"])
        self.assertEqual(failed["payload_sha256"], received["payload_sha256"])
        self.assertEqual(len(list(self.root.glob("payloads/*/response.pb"))), 1)
        gap = datetime.fromisoformat(received["request_started_at_utc"]) - datetime.fromisoformat(failed["finished_at_utc"])
        self.assertGreaterEqual(gap.total_seconds(), 0.05)

    def test_deadline_and_size_limit_leave_no_payload_identity(self):
        url, seen = self.start_server([("blocked", b"", None), (200, self.body, None)])
        timed_out = collector.poll_trip_updates(url, self.root, timeout=10,
                                                request_deadline_seconds=0.7)
        oversized = collector.poll_trip_updates(url, self.root, timeout=10,
                                                max_response_bytes=10,
                                                request_deadline_seconds=5)
        self.assertEqual(len(seen), 2)
        for record in (timed_out, oversized):
            self.saved(record)
            self.assertEqual(record["outcome"], "failed")
            self.assertFalse(record["valid_snapshot"])
            self.assertNotIn("payload_sha256", record)
            self.assertNotIn("received_at_utc", record)
            self.assertIn("finished_at_utc", record)
            self.assertFalse((self.root / "requests" / f"{record['request_id']}.part").exists())
        self.assertEqual(timed_out["error"], "request_deadline_exceeded")
        self.assertEqual(timed_out["observed_size_bytes"], 0)
        self.assertEqual(oversized["error"], "response_too_large")
        self.assertEqual(oversized["observed_size_bytes"], 11)
        self.assertEqual(list(self.root.glob("payloads/*/response.pb")), [])

    def test_other_process_owns_root_before_recovery_or_poll(self):
        code = """
import sys, time
from pathlib import Path
from schedule_truth.vehicle_positions_ownership import own_archive
with own_archive(Path(sys.argv[1])):
    print('owned', flush=True)
    time.sleep(30)
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(sys.path)
        owner = subprocess.Popen([sys.executable, "-B", "-c", code, str(self.root)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.assertEqual(owner.stdout.readline().strip(), "owned")
            with self.assertRaisesRegex(RuntimeError, "already owned"):
                runner.run_trip_updates("http://127.0.0.1:9/trips", self.root,
                                        stop_event=OnePoll(), request_deadline_seconds=1)
            self.assertEqual(self.all_files(), {})
        finally:
            owner.kill()
            owner.communicate(timeout=5)
        runner.run_trip_updates("http://127.0.0.1:9/trips", self.root,
                                stop_event=type("AlreadyStopped", (), {
                                    "is_set": lambda self: True})())
        self.assertEqual(self.all_files(), {})


if __name__ == "__main__":
    unittest.main()
