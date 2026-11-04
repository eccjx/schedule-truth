"""Independent Windows Alerts poll and runner checks with persisted evidence."""

from datetime import datetime, timedelta
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
from schedule_truth import collect_alerts as collector
from schedule_truth import run_alerts as runner
from schedule_truth.vehicle_positions_ownership import own_archive
from test_collect_alerts_independent import alerts_bytes


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


@unittest.skipUnless(os.name == "nt", "Windows worker and ownership only")
class IndependentAlertsRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "alerts"
        self.body = alerts_bytes()

    def files(self):
        return {str(path.relative_to(self.root)): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()}

    def records(self):
        return [json.loads(path.read_text(encoding="utf-8"))
                for path in (self.root / "requests").glob("*.json")]

    def saved(self, record):
        path = self.root / "requests" / f"{record['request_id']}.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), record)
        self.assertEqual(record["feed_type"], "service_alerts")
        self.assertFalse(path.with_suffix(".part").exists())
        for field in ("request_started_at_utc", "finished_at_utc"):
            self.assertEqual(datetime.fromisoformat(record[field]).utcoffset(), timedelta(0))
        return path

    def server(self, responses, stop_event=None):
        pending = list(responses)
        release = threading.Event()
        seen = []
        guard = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                with guard:
                    mode, status, body, declared = pending.pop(0)
                    seen.append((self.path, time.monotonic()))
                if stop_event is not None:
                    stop_event.set()
                if mode == "blocked":
                    release.wait(5)
                    return
                self.send_response(status)
                self.send_header("Content-Length", str(len(body) if declared is None else declared))
                self.end_headers()
                try:
                    if mode == "drip":
                        while not release.is_set():
                            self.wfile.write(b"abcdefgh")
                            self.wfile.flush()
                            release.wait(0.04)
                    else:
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
        return f"http://127.0.0.1:{server.server_port}/Alerts.pb", seen

    def test_incomplete_and_oversized_responses_have_counts_without_identity(self):
        url, seen = self.server([
            ("partial", 200, self.body[:7], len(self.body) + 20),
            ("complete", 200, self.body, None),
        ])
        with own_archive(self.root):
            incomplete = collector.poll_alerts(url, self.root, timeout=10, request_deadline_seconds=5)
            oversized = collector.poll_alerts(url, self.root, timeout=10, max_response_bytes=10,
                                               request_deadline_seconds=5)
        self.assertEqual(len(seen), 2)
        for record in (incomplete, oversized):
            self.saved(record)
            self.assertEqual(record["outcome"], "failed")
            self.assertFalse(record["valid_snapshot"])
            self.assertNotIn("payload_sha256", record)
            self.assertNotIn("payload_path", record)
            self.assertNotIn("received_at_utc", record)
        self.assertEqual(incomplete["partial_staging_size_bytes"], 7)
        self.assertIn("Incomplete response", incomplete["error"])
        self.assertEqual(oversized["error"], "response_too_large")
        self.assertEqual(oversized["observed_size_bytes"], 11)
        self.assertLessEqual(oversized["partial_staging_size_bytes"], 10)
        self.assertEqual(list(self.root.glob("payloads/*/response.pb")), [])

    def test_active_stream_and_blocked_headers_expire_before_socket_timeout(self):
        url, seen = self.server([
            ("drip", 200, b"", 10000),
            ("blocked", 0, b"", None),
        ])
        with own_archive(self.root):
            began = time.monotonic()
            drip = collector.poll_alerts(url, self.root, timeout=10, request_deadline_seconds=0.7)
            drip_elapsed = time.monotonic() - began
            began = time.monotonic()
            blocked = collector.poll_alerts(url, self.root, timeout=10, request_deadline_seconds=0.7)
            blocked_elapsed = time.monotonic() - began
        self.assertEqual(len(seen), 2)
        for record in (drip, blocked):
            self.saved(record)
            self.assertEqual(record["outcome"], "failed")
            self.assertEqual(record["error"], "request_deadline_exceeded")
            self.assertFalse(record["valid_snapshot"])
            self.assertEqual(record["observed_size_bytes"], record["partial_staging_size_bytes"])
            self.assertNotIn("payload_sha256", record)
        self.assertGreater(drip["partial_staging_size_bytes"], 0)
        self.assertEqual(drip["http_status"], 200)
        self.assertEqual(blocked["partial_staging_size_bytes"], 0)
        self.assertLess(drip_elapsed, 4)
        self.assertLess(blocked_elapsed, 4)
        self.assertEqual(list(self.root.glob("payloads/*/response.pb")), [])

    def test_failed_poll_then_success_is_sequential_and_saves_exact_bytes(self):
        url, seen = self.server([
            ("partial", 200, self.body[:5], len(self.body) + 10),
            ("complete", 200, self.body, None),
        ])
        stop = TwoPolls()
        runner.run_alerts(url, self.root, interval_seconds=0.08, timeout=10,
                          request_deadline_seconds=5, stop_event=stop)
        self.assertEqual(stop.waits, [0.08, 0.08])
        self.assertEqual(len(seen), 2)
        failed, success = sorted(self.records(), key=lambda row: row["request_started_at_utc"])
        self.saved(failed)
        self.saved(success)
        self.assertEqual((failed["outcome"], success["outcome"]), ("failed", "received"))
        self.assertNotEqual(failed["request_id"], success["request_id"])
        self.assertNotIn("payload_sha256", failed)
        payload = Path(success["payload_path"])
        self.assertEqual(payload.read_bytes(), self.body)
        self.assertEqual(success["payload_sha256"], sha256(self.body).hexdigest())
        self.assertEqual(success["size_bytes"], len(self.body))
        self.assertEqual(success["feed_timestamp"], 1793659351)
        self.assertEqual(datetime.fromisoformat(success["received_at_utc"]).utcoffset(), timedelta(0))
        self.assertNotEqual(success["feed_timestamp"],
                            int(datetime.fromisoformat(success["received_at_utc"]).timestamp()))
        self.assertFalse(any(isinstance(value, (list, dict)) for value in success.values()))
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(payload.read_bytes())
        self.assertEqual(feed.entity[0].alert.active_period[0].start, 1793660400)
        gap = datetime.fromisoformat(success["request_started_at_utc"]) - datetime.fromisoformat(failed["finished_at_utc"])
        self.assertGreaterEqual(gap.total_seconds(), 0.05)

    def test_restart_recovers_started_and_preserves_completed_evidence(self):
        url, seen = self.server([
            ("complete", 200, self.body, None),
            ("complete", 200, self.body, None),
        ])
        runner.run_alerts(url, self.root, interval_seconds=0, timeout=10,
                          request_deadline_seconds=5, stop_event=OnePoll())
        first = self.records()[0]
        self.saved(first)
        earlier = self.files()
        old = self.root / "requests" / "old.json"
        old.write_text(json.dumps({
            "request_id": "old", "feed_type": "service_alerts",
            "request_started_at_utc": "2026-11-03T00:00:00+00:00",
            "outcome": "started", "valid_snapshot": False,
        }), encoding="utf-8")
        old.with_suffix(".part").write_bytes(b"unfinished")
        runner.run_alerts(url, self.root, interval_seconds=0, timeout=10,
                          request_deadline_seconds=5, stop_event=OnePoll())
        self.assertEqual(len(seen), 2)
        recovered = json.loads(old.read_text(encoding="utf-8"))
        self.assertEqual(recovered["outcome"], "interrupted")
        self.assertEqual(recovered["response_outcome"], "unknown")
        self.assertEqual(recovered["partial_staging_size_bytes"], len(b"unfinished"))
        self.assertFalse(old.with_suffix(".part").exists())
        for relative, evidence in earlier.items():
            path = self.root / relative
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), evidence)
        fresh = [row for row in self.records() if row["request_id"] not in ("old", first["request_id"])]
        self.assertEqual(len(fresh), 1)
        self.assertEqual(fresh[0]["outcome"], "received")
        self.assertEqual(fresh[0]["payload_sha256"], first["payload_sha256"])
        before_stop = self.files()
        class Stopped:
            def is_set(self):
                return True
        runner.run_alerts(url, self.root, stop_event=Stopped())
        self.assertEqual(len(seen), 2)
        self.assertEqual(self.files(), before_stop)

    def test_stop_during_active_request_keeps_deadline_and_skips_next_poll(self):
        stop = threading.Event()
        url, seen = self.server([("blocked", 0, b"", None)], stop_event=stop)
        began = time.monotonic()
        runner.run_alerts(url, self.root, interval_seconds=0, timeout=10,
                          request_deadline_seconds=0.7, stop_event=stop)
        self.assertLess(time.monotonic() - began, 4)
        self.assertEqual(len(seen), 1)
        record = self.records()[0]
        self.saved(record)
        self.assertEqual(record["request_deadline_seconds"], 0.7)
        self.assertEqual(record["error"], "request_deadline_exceeded")
        self.assertEqual(record["observed_size_bytes"], 0)
        self.assertNotIn("payload_sha256", record)

    def test_second_process_cannot_write_owned_root(self):
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
                runner.run_alerts("http://127.0.0.1:9/Alerts.pb", self.root,
                                  stop_event=OnePoll(), request_deadline_seconds=1)
            self.assertEqual(self.files(), {})
        finally:
            owner.kill()
            owner.communicate(timeout=5)
        class Stopped:
            def is_set(self):
                return True
        runner.run_alerts("http://127.0.0.1:9/Alerts.pb", self.root, stop_event=Stopped())
        self.assertEqual(self.files(), {})


if __name__ == "__main__":
    unittest.main()
