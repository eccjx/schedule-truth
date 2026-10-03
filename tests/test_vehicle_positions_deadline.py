"""Real child transport against local slow and blocked HTTP endpoints."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import signal
import subprocess
import os
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from schedule_truth import collect_vehicle_positions as collector
from schedule_truth import run_vehicle_positions as runner
from test_collect_vehicle_positions import payload


class DeadlineTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'archive'
        self.stop = threading.Event()
        self.release = threading.Event()
        self.request_seen = threading.Event()
        self.count = 0
        self.mode = 'blocked'
        self.body = payload()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                owner.count += 1
                owner.request_seen.set()
                if owner.mode == 'ctrl_c':
                    signal.raise_signal(signal.SIGINT)
                if owner.mode == 'shutdown':
                    owner.stop.set()
                if owner.mode in ('blocked', 'shutdown', 'ctrl_c'):
                    owner.release.wait(10)
                    return
                self.send_response(200)
                self.send_header('Content-Length', str(len(owner.body)))
                self.end_headers()
                try:
                    if owner.mode == 'drip':
                        for byte in owner.body:
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                            if owner.release.wait(0.1):
                                return
                    else:
                        self.wfile.write(owner.body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/positions'
        self.addCleanup(self.cleanup_server)

    def cleanup_server(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()

    def check_failure(self, record):
        self.assertEqual(record['outcome'], 'failed')
        self.assertEqual(record['error'], 'request_deadline_exceeded')
        self.assertFalse(record['valid_snapshot'])
        self.assertNotIn('payload_sha256', record)
        self.assertNotIn('received_at_utc', record)
        self.assertIn('finished_at_utc', record)
        self.assertEqual(record['observed_size_bytes'], record['partial_staging_size_bytes'])
        path = self.root / 'requests' / (record['request_id'] + '.json')
        self.assertEqual(json.loads(path.read_text()), record)
        self.assertFalse(path.with_suffix('.part').exists())
        self.assertEqual(list(self.root.glob('payloads/*')), [])

    def test_slow_drip_expires_despite_continued_network_progress(self):
        self.mode = 'drip'
        began = time.monotonic()
        record = collector._poll_vehicle_positions(self.url, self.root, 30, request_deadline_seconds=1)
        elapsed = time.monotonic() - began
        self.check_failure(record)
        self.assertEqual(record['http_status'], 200)
        self.assertGreater(record['observed_size_bytes'], 0)
        self.assertGreaterEqual(elapsed, 0.9)
        self.assertLess(elapsed, 4)

    def test_blocked_headers_do_not_wait_for_socket_timeout(self):
        began = time.monotonic()
        record = collector._poll_vehicle_positions(self.url, self.root, 30, request_deadline_seconds=1)
        self.check_failure(record)
        self.assertEqual(record['observed_size_bytes'], 0)
        self.assertLess(time.monotonic() - began, 4)

    def test_shutdown_does_not_extend_original_deadline_or_start_another_poll(self):
        self.mode = 'shutdown'
        began = time.monotonic()
        runner.run_vehicle_positions(self.url, self.root, timeout=30, stop_event=self.stop,
                                     request_deadline_seconds=1)
        self.assertLess(time.monotonic() - began, 4)
        self.assertEqual(self.count, 1)
        self.check_failure(json.loads(next(self.root.glob('requests/*.json')).read_text()))

    def test_complete_response_before_deadline_preserves_payload(self):
        self.mode = 'complete'
        record = collector._poll_vehicle_positions(self.url, self.root, 30, request_deadline_seconds=5)
        self.assertEqual(record['outcome'], 'received')
        self.assertTrue(record['valid_snapshot'])
        self.assertEqual(Path(record['payload_path']).read_bytes(), self.body)

    def test_ctrl_c_waits_only_for_original_deadline(self):
        self.mode = 'ctrl_c'
        began = time.monotonic()
        with patch.object(sys, 'argv', ['runner', '--url', self.url, '--root', str(self.root),
                                      '--request-deadline-seconds', '1']):
            runner.main()
        self.assertLess(time.monotonic() - began, 4)
        self.assertEqual(self.count, 1)
        self.check_failure(json.loads(next(self.root.glob('requests/*.json')).read_text()))

    def test_runner_crash_also_terminates_network_worker(self):
        code = """
import sys
from pathlib import Path
from schedule_truth import collect_vehicle_positions as c
original = c.subprocess.Popen
def start(*args, **kwargs):
    worker = original(*args, **kwargs)
    print(worker.pid, flush=True)
    return worker
c.subprocess.Popen = start
c._poll_vehicle_positions(sys.argv[1], Path(sys.argv[2]), 30, request_deadline_seconds=30)
"""
        env = os.environ.copy()
        env['PYTHONPATH'] = os.pathsep.join(sys.path)
        parent = subprocess.Popen([sys.executable, '-B', '-c', code, self.url, str(self.root)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = None
        try:
            worker_pid = int(parent.stdout.readline())
            self.assertTrue(self.request_seen.wait(5))
            handle = kernel.OpenProcess(0x100000, False, worker_pid)
            self.assertTrue(handle)
            parent.kill()
            parent.wait(timeout=5)
            self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
        finally:
            if parent.poll() is None:
                parent.kill()
            parent.communicate(timeout=5)
            if handle:
                kernel.CloseHandle(handle)

    def test_startup_record_time_consumes_original_deadline(self):
        save = collector._save_request
        def delayed_save(path, record):
            save(path, record)
            if record['outcome'] == 'started':
                time.sleep(0.2)
        with patch.object(collector, '_save_request', delayed_save):
            record = collector._poll_vehicle_positions(self.url, self.root, 30, request_deadline_seconds=0.1)
        self.check_failure(record)
        self.assertEqual(self.count, 0)


if __name__ == '__main__':
    unittest.main()
