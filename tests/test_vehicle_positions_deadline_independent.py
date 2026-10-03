"""Independent Windows runner checks using real local HTTP and persisted files."""

from datetime import datetime, timedelta
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth import run_vehicle_positions as runner
from test_collect_vehicle_positions import payload


@unittest.skipUnless(os.name == "nt", "Windows runner ownership and worker only")
class IndependentDeadlineTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "archive"
        self.body = payload()
        self.mode = "blocked"
        self.release = threading.Event()
        self.stop = threading.Event()
        self.request_count = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                owner.request_count += 1
                if owner.mode == "interrupt":
                    owner.release.wait(0.6)
                    signal.raise_signal(signal.SIGINT)
                if owner.mode in ("blocked", "interrupt"):
                    owner.release.wait(5)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(owner.body) if owner.mode == "complete" else 10000))
                self.end_headers()
                try:
                    if owner.mode == "drip":
                        while not owner.release.is_set():
                            self.wfile.write(b"abcdefgh")
                            self.wfile.flush()
                            owner.release.wait(0.04)
                    else:
                        self.wfile.write(owner.body)
                        owner.stop.set()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/VehiclePositions.pb"
        self.addCleanup(self.close_server)

    def close_server(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def records(self):
        return [json.loads(path.read_text(encoding="utf-8"))
                for path in (self.root / "requests").glob("*.json")]

    def assert_deadline_record(self, record, partial, no_payload_files=True,
                               expected_deadline=0.7):
        self.assertEqual(record["outcome"], "failed")
        self.assertEqual(record["error"], "request_deadline_exceeded")
        self.assertFalse(record["valid_snapshot"])
        self.assertEqual(record["request_deadline_seconds"], expected_deadline)
        self.assertEqual(record["observed_size_bytes"], partial)
        self.assertEqual(record["partial_staging_size_bytes"], partial)
        self.assertNotIn("payload_sha256", record)
        self.assertNotIn("payload_path", record)
        self.assertNotIn("received_at_utc", record)
        started = datetime.fromisoformat(record["request_started_at_utc"])
        finished = datetime.fromisoformat(record["finished_at_utc"])
        self.assertEqual(started.utcoffset(), timedelta(0))
        self.assertEqual(finished.utcoffset(), timedelta(0))
        self.assertGreater(finished, started)
        request_path = self.root / "requests" / f"{record['request_id']}.json"
        self.assertEqual(json.loads(request_path.read_text(encoding="utf-8")), record)
        self.assertFalse(request_path.with_suffix(".part").exists())
        if no_payload_files:
            self.assertEqual(list(self.root.glob("payloads/*/response.pb")), [])

    def test_active_slow_stream_expires_and_persists_partial_count(self):
        self.mode = "drip"
        began = time.monotonic()
        from schedule_truth.collect_vehicle_positions import _poll_vehicle_positions
        record = _poll_vehicle_positions(self.url, self.root, 10, request_deadline_seconds=0.7)
        self.assert_deadline_record(record, record["observed_size_bytes"])
        self.assertGreater(record["observed_size_bytes"], 0)
        self.assertEqual(record["http_status"], 200)
        self.assertEqual(self.request_count, 1)
        self.assertLess(time.monotonic() - began, 4)

    def test_blocked_headers_expire_before_longer_socket_timeout(self):
        began = time.monotonic()
        from schedule_truth.collect_vehicle_positions import _poll_vehicle_positions
        record = _poll_vehicle_positions(self.url, self.root, 10, request_deadline_seconds=0.7)
        self.assert_deadline_record(record, 0)
        self.assertEqual(self.request_count, 1)
        self.assertLess(time.monotonic() - began, 4)

    def test_ctrl_c_preserves_deadline_and_starts_no_second_poll(self):
        self.mode = "interrupt"
        old_handler = signal.getsignal(signal.SIGINT)
        began = time.monotonic()
        with patch.object(sys, "argv", ["runner", "--url", self.url, "--root", str(self.root),
                                        "--interval-seconds", "0", "--timeout", "10",
                                        "--request-deadline-seconds", "1.5"]):
            runner.main()
        self.assertIs(signal.getsignal(signal.SIGINT), old_handler)
        self.assertEqual(self.request_count, 1)
        self.assertEqual(len(self.records()), 1)
        self.assert_deadline_record(self.records()[0], 0, expected_deadline=1.5)
        # The signal arrives well into the request. A new 1.5-second clock
        # would make this considerably later than the original deadline.
        self.assertLess(time.monotonic() - began, 1.95)

    def test_complete_response_then_restart_preserves_old_request(self):
        self.mode = "complete"
        runner.run_vehicle_positions(self.url, self.root, timeout=10,
                                     request_deadline_seconds=2, stop_event=self.stop,
                                     interval_seconds=0)
        records = self.records()
        self.assertEqual(len(records), 1)
        first = records[0]
        self.assertEqual(first["outcome"], "received")
        self.assertTrue(first["valid_snapshot"])
        self.assertEqual(first["request_deadline_seconds"], 2)
        self.assertEqual(first["payload_sha256"], sha256(self.body).hexdigest())
        payload_path = Path(first["payload_path"])
        self.assertEqual(payload_path.read_bytes(), self.body)
        first_path = self.root / "requests" / f"{first['request_id']}.json"
        self.assertEqual(json.loads(first_path.read_text(encoding="utf-8")), first)
        self.assertFalse(first_path.with_suffix(".part").exists())
        original_bytes = first_path.read_bytes()

        self.mode = "blocked"
        from schedule_truth.collect_vehicle_positions import _poll_vehicle_positions
        expired = _poll_vehicle_positions(self.url, self.root, 10, request_deadline_seconds=0.7)
        self.assert_deadline_record(expired, 0, no_payload_files=False)
        expired_path = self.root / "requests" / f"{expired['request_id']}.json"
        expired_bytes = expired_path.read_bytes()

        old_path = self.root / "requests" / "unfinished.json"
        old_path.write_text(json.dumps({"request_id": "unfinished", "request_url": self.url,
                                        "request_started_at_utc": "2026-10-02T00:00:00+00:00",
                                        "outcome": "started", "valid_snapshot": False}), encoding="utf-8")
        old_path.with_suffix(".part").write_bytes(b"lost partial")
        self.stop.clear()
        self.mode = "complete"
        runner.run_vehicle_positions(self.url, self.root, timeout=10,
                                     request_deadline_seconds=2, stop_event=self.stop,
                                     interval_seconds=0)
        recovered = json.loads(old_path.read_text(encoding="utf-8"))
        self.assertEqual(recovered["outcome"], "interrupted")
        self.assertEqual(recovered["partial_staging_size_bytes"], len(b"lost partial"))
        self.assertFalse(old_path.with_suffix(".part").exists())
        self.assertEqual(first_path.read_bytes(), original_bytes)
        self.assertEqual(expired_path.read_bytes(), expired_bytes)
        self.assertEqual(payload_path.read_bytes(), self.body)
        self.assertEqual(len(self.records()), 4)
        self.assertEqual(self.request_count, 3)

    def test_cross_process_owner_blocks_poll_and_releases_after_exit(self):
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
                runner.run_vehicle_positions(self.url, self.root, timeout=10,
                                             request_deadline_seconds=0.7,
                                             stop_event=self.stop)
            self.assertEqual(self.request_count, 0)
            self.assertEqual(self.records(), [])
        finally:
            owner.kill()
            owner.communicate(timeout=5)
        self.stop.set()
        runner.run_vehicle_positions(self.url, self.root, timeout=10,
                                     request_deadline_seconds=0.7,
                                     stop_event=self.stop)
        self.assertEqual(self.records(), [])


if __name__ == "__main__":
    unittest.main()
