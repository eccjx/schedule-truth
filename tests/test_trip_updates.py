"""Trip Updates exact-byte persistence, replay, and runner integration."""

from datetime import datetime, timezone, timedelta
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from google.transit import gtfs_realtime_pb2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from schedule_truth import collect_trip_updates as collector
from schedule_truth import run_trip_updates as runner
from schedule_truth.vehicle_positions_ownership import own_archive


def payload(times=True):
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = '2.0'
    if times:
        feed.header.timestamp = 1790980169
    entity = feed.entity.add()
    entity.id = '78258766'
    entity.trip_update.trip.trip_id = '0078258766'
    entity.trip_update.trip.start_date = '20261002'
    if times:
        entity.trip_update.timestamp = 1790980159
    stop = entity.trip_update.stop_time_update.add()
    stop.stop_id = '65'
    stop.stop_sequence = 1
    if times:
        stop.departure.time = 1790982300
        stop.arrival.time = 1790970000
    return feed.SerializeToString()


class TripUpdatesTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'trip_updates'
        self.started = datetime(2026, 10, 2, 22, 30, tzinfo=timezone.utc)
        self.received = self.started + timedelta(seconds=1, microseconds=123456)
        self.body = payload()

    def persist(self, request_id='one', body=None, status=200, received=None):
        return collector.persist_trip_updates_response(self.root, request_id,
                  self.body if body is None else body, status, self.started,
                  self.received if received is None else received)

    def test_duplicate_bytes_separate_requests_and_all_time_meanings(self):
        one = self.persist()
        two = self.persist('two', received=self.received + timedelta(seconds=30))
        self.assertNotEqual(one['request_id'], two['request_id'])
        self.assertNotEqual(one['received_at_utc'], two['received_at_utc'])
        self.assertEqual(one['payload_sha256'], hashlib.sha256(self.body).hexdigest())
        self.assertEqual(two['payload_sha256'], one['payload_sha256'])
        self.assertEqual(Path(one['payload_path']).read_bytes(), self.body)
        self.assertEqual(len(list(self.root.glob('payloads/*/response.pb'))), 1)
        self.assertEqual(one['feed_type'], 'trip_updates')
        self.assertEqual(one['feed_timestamp'], 1790980169)
        self.assertNotIn('trip_updates', one)
        for value in one.values():
            self.assertNotIsInstance(value, (list, dict))
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(Path(one['payload_path']).read_bytes())
        update = feed.entity[0].trip_update
        self.assertEqual(update.timestamp, 1790980159)
        self.assertEqual(update.trip.trip_id, '0078258766')
        self.assertEqual(update.stop_time_update[0].departure.time, 1790982300)
        self.assertEqual(update.stop_time_update[0].arrival.time, 1790970000)
        self.assertNotIn('actual', json.dumps(one))

    def test_identical_replay_does_not_rewrite_either_file(self):
        first = self.persist()
        paths = [self.root / 'requests' / 'one.json', Path(first['payload_path'])]
        before = {}
        for path in paths:
            os.utime(path, (946684800, 946684800))
            before[path] = (path.read_bytes(), path.stat().st_mtime_ns)
        self.assertEqual(self.persist(), first)
        for path in paths:
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before[path])

    def test_changed_hash_status_or_receipt_is_conflict_without_writes(self):
        self.persist()
        before = (self.root / 'requests' / 'one.json').read_bytes()
        for kwargs in ({'body': payload(False)}, {'status': 503},
                       {'received': self.received + timedelta(microseconds=1)}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(ValueError, 'Conflicting'):
                    self.persist(**kwargs)
                self.assertEqual((self.root / 'requests' / 'one.json').read_bytes(), before)
        self.assertEqual(len(list(self.root.glob('payloads/*/response.pb'))), 1)

    def test_historical_expanded_record_replay_preserves_history(self):
        record = self.persist()
        record['trip_updates'] = [{'trip_id': '0078258766', 'stop_time_updates': [
            {'stop_id': '65', 'arrival_time': 1790970000}]}]
        path = self.root / 'requests' / 'one.json'
        path.write_text(json.dumps(record), encoding='utf-8')
        os.utime(path, (946684800, 946684800))
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        self.assertEqual(self.persist(), record)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        self.assertEqual(Path(record['payload_path']).read_bytes(), self.body)

    def test_large_feed_keeps_request_scalar_and_payload_complete(self):
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(self.body)
        first = gtfs_realtime_pb2.FeedEntity()
        first.CopyFrom(feed.entity[0])
        for number in range(1000):
            entity = feed.entity.add()
            entity.CopyFrom(first)
            entity.id = str(number)
        body = feed.SerializeToString()
        record = self.persist(body=body)
        saved = (self.root / 'requests' / 'one.json').read_bytes()
        self.assertEqual(json.loads(saved), record)
        for value in record.values():
            self.assertNotIsInstance(value, (list, dict))
        self.assertLess(len(saved), 2000)
        self.assertEqual(Path(record['payload_path']).read_bytes(), body)
        self.assertEqual(record['payload_sha256'], hashlib.sha256(body).hexdigest())

    def test_started_record_can_complete_and_retains_url(self):
        path = self.root / 'requests' / 'one.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'request_id': 'one', 'feed_type': 'trip_updates',
                                   'request_url': 'https://example.test/TripUpdates.pb',
                                   'request_started_at_utc': self.started.isoformat(), 'outcome': 'started'}))
        result = self.persist()
        self.assertEqual(result['outcome'], 'received')
        self.assertEqual(result['request_url'], 'https://example.test/TripUpdates.pb')

    def test_timeout_without_payload_rejects_completion_before_writes(self):
        path = self.root / 'requests' / 'one.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'request_id': 'one', 'feed_type': 'trip_updates',
                                   'request_started_at_utc': self.started.isoformat(),
                                   'outcome': 'failed', 'error': 'request_deadline_exceeded',
                                   'finished_at_utc': self.received.isoformat(),
                                   'valid_snapshot': False, 'observed_size_bytes': 0}))
        os.utime(path, (946684800, 946684800))
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        with patch.object(collector, '_save_request') as save, patch.object(Path, 'mkdir') as mkdir:
            with self.assertRaisesRegex(ValueError, 'Terminal request without payload.*one'):
                self.persist()
            save.assert_not_called()
            mkdir.assert_not_called()
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        self.assertEqual(sorted(self.root.rglob('*')), [path.parent, path])

    def test_interruption_without_payload_rejects_completion_before_writes(self):
        path = self.root / 'requests' / 'one.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'request_id': 'one', 'feed_type': 'trip_updates',
                                   'request_started_at_utc': self.started.isoformat(),
                                   'outcome': 'interrupted',
                                   'finished_at_utc': self.received.isoformat(),
                                   'valid_snapshot': False, 'partial_staging_existed': True,
                                   'partial_staging_size_bytes': 7}))
        os.utime(path, (946684800, 946684800))
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        with patch.object(collector, '_save_request') as save, patch.object(Path, 'mkdir') as mkdir:
            with self.assertRaisesRegex(ValueError, 'Terminal request without payload.*one'):
                self.persist()
            save.assert_not_called()
            mkdir.assert_not_called()
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        self.assertEqual(sorted(self.root.rglob('*')), [path.parent, path])

    def test_corrupt_existing_payload_rejected_before_request_link(self):
        one = self.persist()
        path = Path(one['payload_path'])
        path.write_bytes(b'altered')
        for request_id in ('one', 'two'):
            with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
                self.persist(request_id)
        self.assertEqual(path.read_bytes(), b'altered')
        self.assertFalse((self.root / 'requests' / 'two.json').exists())

    def test_missing_terminal_payload_is_integrity_error_without_repair(self):
        one = self.persist()
        record_path = self.root / 'requests' / 'one.json'
        before = record_path.read_bytes()
        path = Path(one['payload_path'])
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing terminal payload'):
            self.persist()
        self.assertFalse(path.exists())
        self.assertEqual(record_path.read_bytes(), before)

    def test_payload_exists_before_finished_record_and_failed_write_leaves_no_link(self):
        def fail_save(path, record):
            self.assertEqual(Path(record['payload_path']).read_bytes(), self.body)
            raise OSError('record write failed')
        with patch.object(collector, '_save_request', fail_save):
            with self.assertRaises(OSError):
                self.persist()
        self.assertFalse((self.root / 'requests' / 'one.json').exists())

    def test_malformed_and_http_error_bodies_are_exact_failed_evidence(self):
        for name, body, status in (('bad', b'\xffbad', 200), ('http', self.body, 503)):
            record = self.persist(name, body, status)
            self.assertEqual(record['outcome'], 'failed')
            self.assertFalse(record['valid_snapshot'])
            self.assertTrue(record['error'])
            self.assertEqual(Path(record['payload_path']).read_bytes(), body)
            self.assertEqual(self.persist(name, body, status), record)

    def test_absent_source_times_stay_null(self):
        record = self.persist(body=payload(False))
        self.assertIsNone(record['feed_timestamp'])
        self.assertNotIn('trip_updates', record)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(Path(record['payload_path']).read_bytes())
        update = feed.entity[0].trip_update
        self.assertFalse(update.HasField('timestamp'))
        self.assertFalse(update.stop_time_update[0].HasField('departure'))

    def test_runner_persists_label_before_poll_and_uses_default_cadence(self):
        stop = threading.Event()
        calls = []
        def receive(url, staging, timeout, limit, deadline):
            started = json.loads(staging.with_suffix('.json').read_text())
            self.assertEqual(started['feed_type'], 'trip_updates')
            self.assertEqual(started['request_url'], url)
            self.assertEqual(started['outcome'], 'started')
            calls.append(started['request_id'])
            if len(calls) == 1:
                return {'complete': False, 'request_error': 'TimeoutError: no bytes'}
            staging.write_bytes(self.body)
            stop.set()
            return {'complete': True, 'request_error': None, 'http_status': 200,
                    'received_at_utc': self.received.isoformat()}
        with patch.object(collector, '_receive_with_deadline', receive), patch.object(stop, 'wait', side_effect=lambda seconds: stop.is_set()) as wait:
            runner.run_trip_updates('https://example.test/trips', self.root, stop_event=stop)
        self.assertEqual(len(set(calls)), 2)
        self.assertEqual(wait.call_args_list[0].args, (30,))
        records = [json.loads(path.read_text()) for path in self.root.glob('requests/*.json')]
        self.assertEqual(sorted(row['outcome'] for row in records), ['failed', 'received'])
        self.assertTrue(all(row['feed_type'] == 'trip_updates' for row in records))

    def test_partial_failures_retain_counts_without_payload(self):
        for reason in ('request_deadline_exceeded', 'response_too_large'):
            def receive(url, staging, *args):
                staging.write_bytes(b'abc')
                return {'complete': False, 'request_error': reason, 'http_status': 200, 'observed_size_bytes': 4}
            with patch.object(collector, '_receive_with_deadline', receive):
                record = collector.poll_trip_updates('https://example.test/trips', self.root)
            self.assertEqual(record['error'], reason)
            self.assertNotIn('payload_sha256', record)
            self.assertEqual(record['partial_staging_size_bytes'], 3)
            self.assertFalse(list(self.root.glob('requests/*.part')))

    def test_ownership_and_dedicated_root_checked_before_recovery(self):
        with own_archive(self.root):
            with patch.object(runner, 'recover_started_requests') as recover:
                with self.assertRaisesRegex(RuntimeError, 'already owned'):
                    runner.run_trip_updates('https://example.test/trips', self.root)
                recover.assert_not_called()
        path = self.root / 'requests' / 'vehicle.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'outcome': 'started'}))
        with self.assertRaisesRegex(ValueError, 'dedicated Trip Updates'):
            runner.run_trip_updates('https://example.test/trips', self.root)
        self.assertEqual(json.loads(path.read_text()), {'outcome': 'started'})

    def test_restart_marks_old_request_interrupted_before_new_poll(self):
        path = self.root / 'requests' / 'old.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'request_id': 'old', 'feed_type': 'trip_updates', 'outcome': 'started',
                                   'request_started_at_utc': self.started.isoformat()}))
        path.with_suffix('.part').write_bytes(b'partial')
        stop = threading.Event()
        def poll(*args):
            recovered = json.loads(path.read_text())
            self.assertEqual(recovered['outcome'], 'interrupted')
            self.assertEqual(recovered['partial_staging_size_bytes'], 7)
            self.assertFalse(path.with_suffix('.part').exists())
            stop.set()
        with patch.object(runner, 'poll_trip_updates', poll):
            runner.run_trip_updates('https://example.test/trips', self.root, stop_event=stop)

    def test_real_transport_worker_links_trip_updates_request(self):
        body = self.body
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        stop = threading.Event()
        try:
            def wait(seconds):
                stop.set()
                return True
            with patch.object(stop, 'wait', wait):
                runner.run_trip_updates(f'http://127.0.0.1:{server.server_port}/trips', self.root,
                                       stop_event=stop, request_deadline_seconds=5)
            record = json.loads(next(self.root.glob('requests/*.json')).read_text())
            self.assertEqual(record['feed_type'], 'trip_updates')
            self.assertEqual(record['outcome'], 'received')
            self.assertNotIn('trip_updates', record)
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(Path(record['payload_path']).read_bytes())
            self.assertEqual(feed.entity[0].trip_update.trip.trip_id, '0078258766')
            self.assertEqual(Path(record['payload_path']).read_bytes(), body)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
