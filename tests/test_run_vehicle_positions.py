"""Runner cadence, shutdown, limits, and real Windows process ownership."""

import io
import json
import os
from pathlib import Path
import subprocess
import signal
import gc
from types import SimpleNamespace
import sys
from tempfile import TemporaryDirectory
import threading
import tracemalloc
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from schedule_truth import collect_vehicle_positions as collector
from schedule_truth import run_vehicle_positions as runner
from schedule_truth.vehicle_positions_ownership import own_archive
from test_collect_vehicle_positions import payload


class RunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'archive'
        self.stop = threading.Event()
        self.url = 'https://example.test/positions.pb'
        # Existing unit tests mock transport in this process; deadline tests use
        # real worker processes and local HTTP servers in a separate test file.
        transport = patch.object(collector, '_receive_with_deadline',
                                 new=lambda url, path, timeout, limit, deadline:
                                 collector._receive_vehicle_positions(url, path, timeout, limit))
        transport.start()
        self.addCleanup(transport.stop)

    def test_recovery_immediate_poll_and_equal_cadence_after_failure_and_success(self):
        order = []
        def recover(root):
            order.append('recover')
        def poll(*args):
            order.append('poll')
            return {'outcome': 'failed' if order.count('poll') == 1 else 'received'}
        def wait(seconds):
            order.append(seconds)
            return order.count('poll') == 2
        with patch.object(runner, 'recover_started_requests', recover), patch.object(runner, '_poll_vehicle_positions', poll), patch.object(self.stop, 'wait', wait):
            runner.run_vehicle_positions(self.url, self.root, stop_event=self.stop)
        self.assertEqual(order, ['recover', 'poll', 15, 'poll', 15])

    def test_stop_during_active_response_or_timeout_finishes_record_and_exits(self):
        for timed_out in (False, True):
            with self.subTest(timed_out=timed_out):
                self.stop.clear()
                body = payload()
                response = Mock(status=200, reason='OK')
                response.getheader.return_value = str(len(body))
                stream = io.BytesIO(body)
                def read(size):
                    self.stop.set()
                    if timed_out:
                        raise TimeoutError('socket timeout')
                    return stream.read(size)
                response.read.side_effect = read
                connection = Mock()
                connection.getresponse.return_value = response
                with patch.object(collector, 'HTTPSConnection', return_value=connection):
                    runner.run_vehicle_positions(self.url, self.root, stop_event=self.stop)
                connection.request.assert_called_once()
        records = [json.loads(path.read_text()) for path in self.root.glob('requests/*.json')]
        self.assertEqual(sorted(record['outcome'] for record in records), ['failed', 'received'])
        self.assertTrue(all('finished_at_utc' in record for record in records))

    def test_stop_during_wait_does_not_poll_again(self):
        def wait(seconds):
            self.stop.set()
            return True
        with patch.object(runner, '_poll_vehicle_positions') as poll, patch.object(self.stop, 'wait', wait):
            runner.run_vehicle_positions(self.url, self.root, stop_event=self.stop)
        poll.assert_called_once()

    def test_size_boundary_and_unadvertised_oversize(self):
        body = payload()
        for limit, expected in ((len(body), 'received'), (len(body) - 1, 'failed')):
            with self.subTest(limit=limit):
                response = Mock(status=200, reason='OK')
                response.getheader.return_value = None
                response.read.side_effect = io.BytesIO(body).read
                connection = Mock()
                connection.getresponse.return_value = response
                with patch.object(collector, 'HTTPSConnection', return_value=connection):
                    record = collector._poll_vehicle_positions(self.url, self.root, 30, limit)
                self.assertEqual(record['outcome'], expected)
                saved = self.root / 'requests' / (record['request_id'] + '.json')
                self.assertEqual(json.loads(saved.read_text()), record)
                self.assertFalse(saved.with_suffix('.part').exists())
                if expected == 'failed':
                    self.assertEqual(record['error'], 'response_too_large')
                    self.assertEqual(record['observed_size_bytes'], limit + 1)
                    self.assertNotIn('payload_sha256', record)
                    self.assertFalse(record['valid_snapshot'])
                    response.read.assert_called_once_with(limit + 1)

    def test_oversize_partial_exception_and_http_error_get_no_identity(self):
        from http.client import IncompleteRead
        for incomplete in (False, True):
            response = Mock(status=503, reason='error')
            response.getheader.return_value = None
            response.read.side_effect = [IncompleteRead(b'abcd')] if incomplete else io.BytesIO(b'abcd').read
            connection = Mock()
            connection.getresponse.return_value = response
            with patch.object(collector, 'HTTPSConnection', return_value=connection):
                record = collector._poll_vehicle_positions(self.url, self.root, 30, 3)
            self.assertEqual(record['error'], 'response_too_large')
            self.assertEqual(record['http_status'], 503)
            self.assertEqual(record['observed_size_bytes'], 4)
            self.assertNotIn('payload_sha256', record)
        self.assertEqual(list(self.root.glob('payloads/*')), [])

    def test_ownership_precedes_recovery_and_blocks_finite_writer(self):
        with own_archive(self.root):
            with patch.object(runner, 'recover_started_requests') as recover:
                with self.assertRaisesRegex(RuntimeError, 'already owned'):
                    runner.run_vehicle_positions(self.url, self.root, stop_event=self.stop)
                recover.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, 'already owned'):
                collector.collect_vehicle_positions(self.url, self.root, 0, 0)
            with own_archive(self.root.parent / 'other'):
                pass
        self.assertFalse(self.root.exists())
        with own_archive(self.root):
            pass

    def test_ownership_released_on_exception(self):
        with patch.object(runner, 'recover_started_requests', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                runner.run_vehicle_positions(self.url, self.root)
        with own_archive(self.root):
            pass

    def test_process_crash_releases_ownership_then_recovery_runs(self):
        code = """
import json, sys, time
from pathlib import Path
from schedule_truth.vehicle_positions_ownership import own_archive
root = Path(sys.argv[1])
with own_archive(root):
    folder = root / 'requests'
    folder.mkdir(parents=True)
    (folder / 'old.json').write_text(json.dumps({'request_id':'old','outcome':'started','request_started_at_utc':'2026-10-02T00:00:00+00:00'}))
    (folder / 'old.part').write_bytes(b'partial')
    print('owned', flush=True)
    time.sleep(60)
"""
        env = os.environ.copy()
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src') + os.pathsep + env.get('PYTHONPATH', '')
        process = subprocess.Popen([sys.executable, '-B', '-c', code, str(self.root)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'owned')
            with patch.object(runner, 'recover_started_requests') as recover:
                with self.assertRaisesRegex(RuntimeError, 'already owned'):
                    runner.run_vehicle_positions(self.url, self.root)
                recover.assert_not_called()
            process.kill()
            process.wait(timeout=10)
            self.stop.set()
            runner.run_vehicle_positions(self.url, self.root, stop_event=self.stop)
            record = json.loads((self.root / 'requests' / 'old.json').read_text())
            self.assertEqual(record['outcome'], 'interrupted')
            self.assertEqual(record['partial_staging_size_bytes'], 7)
            self.assertFalse((self.root / 'requests' / 'old.part').exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            process.stdout.close()
            process.stderr.close()

    def test_sustained_runner_does_not_retain_poll_results(self):
        count = 0
        samples = []
        def poll(*args):
            nonlocal count
            count += 1
            if count in (100, 1000, 5000):
                samples.append(tracemalloc.get_traced_memory()[0])
            if count == 5000:
                self.stop.set()
            return {'body': bytearray(256 * 1024)}
        tracemalloc.start()
        try:
            with patch.object(runner, '_poll_vehicle_positions', poll):
                runner.run_vehicle_positions(self.url, self.root, interval_seconds=0, stop_event=self.stop)
            self.assertEqual(count, 5000)
            self.assertLess(max(samples) - min(samples), 64 * 1024)
        finally:
            tracemalloc.stop()

    def test_cli_signal_finishes_active_poll_and_restores_handler(self):
        body = payload()
        stream = io.BytesIO(body)
        response = Mock(status=200, reason='OK')
        response.getheader.return_value = str(len(body))
        def read(size):
            signal.raise_signal(signal.SIGINT)
            return stream.read(size)
        response.read.side_effect = read
        connection = Mock()
        connection.getresponse.return_value = response
        original = signal.getsignal(signal.SIGINT)
        with patch.object(sys, 'argv', ['runner', '--url', self.url, '--root', str(self.root)]), patch.object(collector, 'HTTPSConnection', return_value=connection):
            runner.main()
        self.assertIs(signal.getsignal(signal.SIGINT), original)
        connection.request.assert_called_once()
        record = json.loads(next(self.root.glob('requests/*.json')).read_text())
        self.assertEqual(record['outcome'], 'received')

    def test_sustained_persistence_memory_stays_stable(self):
        body = payload()
        count = 0
        samples = []
        def connection(*args, **kwargs):
            nonlocal count
            count += 1
            if count in (30, 100, 200):
                gc.collect()
                samples.append(tracemalloc.get_traced_memory()[0])
            if count == 200:
                self.stop.set()
            stream = io.BytesIO(body)
            response = SimpleNamespace(status=200, reason='OK', read=stream.read,
                                       getheader=lambda name: str(len(body)))
            return SimpleNamespace(request=lambda *args: None, close=lambda: None,
                                   getresponse=lambda: response)
        tracemalloc.start()
        try:
            with patch.object(collector, 'HTTPSConnection', connection):
                runner.run_vehicle_positions(self.url, self.root, interval_seconds=0, stop_event=self.stop)
            self.assertEqual(count, 200)
            self.assertEqual(len(list(self.root.glob('requests/*.json'))), 200)
            self.assertEqual(len(list(self.root.glob('payloads/*/response.pb'))), 1)
            self.assertLess(max(samples) - min(samples), 256 * 1024)
        finally:
            tracemalloc.stop()


if __name__ == '__main__':
    unittest.main()
