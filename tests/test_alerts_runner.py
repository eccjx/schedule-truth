"""Alerts polling, restart, ownership, and continuous-runner checks."""

from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import signal
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from schedule_truth import collect_alerts as collector
from schedule_truth import run_alerts as runner
from schedule_truth.vehicle_positions_ownership import own_archive
from test_collect_alerts_independent import alerts_bytes


class AlertsRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'alerts'
        self.body = alerts_bytes()
        self.url = 'https://example.test/Alerts.pb'

    def test_complete_bodies_persist_exact_evidence_and_distinct_requests(self):
        received = []
        bodies = [(200, self.body), (200, self.body), (503, self.body), (200, b'\xffbad')]
        def receive(url, staging, timeout, limit, deadline):
            started = json.loads(staging.with_suffix('.json').read_text())
            self.assertEqual(started['outcome'], 'started')
            self.assertEqual(started['feed_type'], 'service_alerts')
            self.assertEqual(started['request_url'], self.url)
            self.assertEqual((timeout, limit), (30, 10 * 1024 * 1024))
            status, body = bodies[len(received)]
            staging.write_bytes(body)
            receipt = datetime.now(timezone.utc).isoformat()
            received.append(receipt)
            return {'complete': True, 'http_status': status, 'received_at_utc': receipt}
        with own_archive(self.root), patch.object(collector, '_receive_with_deadline', receive):
            records = []
            for index in range(4):
                record = collector.poll_alerts(self.url, self.root)
                records.append(record)
                status, body = bodies[index]
                self.assertEqual(Path(record['payload_path']).read_bytes(), body)
                self.assertEqual(record['payload_sha256'], sha256(body).hexdigest())
                self.assertEqual(record['received_at_utc'], received[index])
                self.assertEqual(record['http_status'], status)
                self.assertEqual(record['valid_snapshot'], index < 2)
                self.assertEqual(record['outcome'], 'received' if index < 2 else 'failed')
                self.assertEqual(json.loads((self.root / 'requests' / (record['request_id'] + '.json')).read_text()), record)
                for value in record.values():
                    self.assertNotIsInstance(value, (dict, list))
        self.assertEqual(len({row['request_id'] for row in records}), 4)
        self.assertEqual(len(list(self.root.glob('payloads/*/response.pb'))), 2)
        self.assertEqual(records[0]['feed_timestamp'], 1793659351)
        self.assertFalse(list(self.root.glob('requests/*.part')))

    def test_incomplete_bodies_never_call_persistence(self):
        for reason, partial, observed in [('TimeoutError: no bytes', None, None),
                                          ('HTTPException: incomplete', b'abc', None),
                                          ('request_deadline_exceeded', b'abc', None),
                                          ('response_too_large', b'abc', 4)]:
            with self.subTest(reason=reason):
                def receive(url, staging, *args):
                    if partial is not None:
                        staging.write_bytes(partial)
                    result = {'complete': False, 'request_error': reason, 'http_status': 200}
                    if observed is not None:
                        result['observed_size_bytes'] = observed
                    return result
                with own_archive(self.root), patch.object(collector, '_receive_with_deadline', receive), patch.object(collector, 'persist_alerts_response') as persist:
                    record = collector.poll_alerts(self.url, self.root)
                persist.assert_not_called()
                self.assertEqual(record['outcome'], 'failed')
                self.assertEqual(record['error'], reason)
                self.assertEqual(record['partial_staging_size_bytes'], len(partial or b''))
                self.assertFalse(record['valid_snapshot'])
                self.assertNotIn('payload_sha256', record)
                self.assertNotIn('payload_path', record)
                self.assertNotIn('received_at_utc', record)
                self.assertIn('finished_at_utc', record)
                if observed is not None:
                    self.assertEqual(record['observed_size_bytes'], observed)
        self.assertFalse(list(self.root.glob('requests/*.part')))
        self.assertFalse((self.root / 'payloads').exists())

    def test_runner_recovers_then_polls_immediately_and_waits_after_failure(self):
        path = self.root / 'requests' / 'old.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'request_id': 'old', 'feed_type': 'service_alerts', 'outcome': 'started'}))
        path.with_suffix('.part').write_bytes(b'partial')
        stop = threading.Event()
        events = []
        def receive(url, staging, *args):
            recovered = json.loads(path.read_text())
            self.assertEqual(recovered['outcome'], 'interrupted')
            self.assertEqual(recovered['response_outcome'], 'unknown')
            self.assertEqual(recovered['partial_staging_size_bytes'], 7)
            self.assertFalse(path.with_suffix('.part').exists())
            self.assertNotEqual(staging.stem, 'old')
            events.append('poll')
            return {'complete': False, 'request_error': 'TimeoutError'}
        def wait(seconds):
            events.append(seconds)
            return len(events) == 4
        with patch.object(collector, '_receive_with_deadline', receive), patch.object(stop, 'wait', wait):
            self.assertIsNone(runner.run_alerts(self.url, self.root, stop_event=stop))
        self.assertEqual(events, ['poll', 60, 'poll', 60])
        self.assertEqual(len(list(self.root.glob('requests/*.json'))), 3)

    def test_ownership_and_feed_separation_precede_recovery(self):
        with own_archive(self.root), patch.object(runner, 'recover_started_requests') as recover:
            with self.assertRaisesRegex(RuntimeError, 'already owned'):
                runner.run_alerts(self.url, self.root)
            recover.assert_not_called()
        path = self.root / 'requests' / 'other.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'feed_type': 'trip_updates', 'outcome': 'started'}))
        before = path.read_bytes()
        with patch.object(runner, 'recover_started_requests') as recover:
            with self.assertRaisesRegex(ValueError, 'dedicated Alerts'):
                runner.run_alerts(self.url, self.root)
            recover.assert_not_called()
        self.assertEqual(path.read_bytes(), before)

    def test_shutdown_during_request_keeps_original_deadline_and_saves_outcome(self):
        stop = threading.Event()
        def receive(url, staging, timeout, limit, deadline):
            self.assertEqual(deadline, 220)
            stop.set()
            staging.write_bytes(b'partial')
            return {'complete': False, 'request_error': 'request_deadline_exceeded'}
        with patch.object(collector.time, 'monotonic', return_value=100), patch.object(collector, '_receive_with_deadline', side_effect=receive) as receive_mock:
            runner.run_alerts(self.url, self.root, stop_event=stop)
        self.assertEqual(receive_mock.call_count, 1)
        record = json.loads(next(self.root.glob('requests/*.json')).read_text())
        self.assertEqual(record['error'], 'request_deadline_exceeded')
        self.assertEqual(record['observed_size_bytes'], 7)
        self.assertIn('finished_at_utc', record)

    def test_invalid_configuration_rejects_before_ownership(self):
        for kwargs in ({'interval_seconds': -1}, {'timeout': 0},
                       {'max_response_bytes': -1}, {'request_deadline_seconds': 0}):
            with self.subTest(kwargs=kwargs), patch.object(runner, 'own_archive') as own:
                with self.assertRaises(ValueError):
                    runner.run_alerts(self.url, self.root, **kwargs)
                own.assert_not_called()

    def test_cli_signal_sets_stop_and_restores_handlers(self):
        handlers = {}
        def install(number, handler):
            handlers[number] = handler
            return signal.SIG_DFL
        def run(url, root, interval, timeout, limit, stop, deadline):
            self.assertEqual((interval, timeout, limit, deadline), (60, 30, 10485760, 120))
            self.assertFalse(stop.is_set())
            handlers[signal.SIGINT](signal.SIGINT, None)
            self.assertTrue(stop.is_set())
        with patch.object(sys, 'argv', ['run_alerts', '--url', self.url, '--root', str(self.root)]), patch.object(runner.signal, 'signal', install), patch.object(runner, 'run_alerts', run):
            runner.main()
        self.assertTrue(all(value == signal.SIG_DFL for value in handlers.values()))

    def test_real_worker_success_incomplete_and_oversize(self):
        body = self.body
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body[:3] if self.path == '/partial' else body)
                self.close_connection = True
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}'
            stop = threading.Event()
            with patch.object(stop, 'wait', return_value=True) as wait:
                runner.run_alerts(url + '/ok', self.root, interval_seconds=0.25, stop_event=stop)
            wait.assert_called_once_with(0.25)
            with own_archive(self.root):
                partial = collector.poll_alerts(url + '/partial', self.root, request_deadline_seconds=5)
                large = collector.poll_alerts(url + '/large', self.root, max_response_bytes=10, request_deadline_seconds=5)
            self.assertEqual(partial['partial_staging_size_bytes'], 3)
            self.assertEqual(large['observed_size_bytes'], 11)
            for record in (partial, large):
                self.assertEqual(record['outcome'], 'failed')
                self.assertNotIn('payload_sha256', record)
            payloads = list(self.root.glob('payloads/*/response.pb'))
            self.assertEqual(len(payloads), 1)
            self.assertEqual(payloads[0].read_bytes(), body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
