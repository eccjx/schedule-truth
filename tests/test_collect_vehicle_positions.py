"""Mock HTTP and sleep; exercise real Protobuf, staging, and persisted records."""

from datetime import datetime, timezone, timedelta
import hashlib
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from google.transit import gtfs_realtime_pb2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from schedule_truth import collect_vehicle_positions as collector


def payload(timestamps=True):
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = '2.0'
    if timestamps:
        feed.header.timestamp = 1790876142
    entity = feed.entity.add()
    entity.id = 'entity-01'
    entity.vehicle.vehicle.id = '0001'
    entity.vehicle.position.latitude = 42.3
    entity.vehicle.position.longitude = -71.1
    if timestamps:
        entity.vehicle.timestamp = 1790876101
    return feed.SerializeToString()


class VehiclePositionsCollectorTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'vehicle_positions'
        self.url = 'https://example.test/VehiclePositions.pb?sample=1'
        self.connection = Mock()
        patcher = patch.object(collector, 'HTTPSConnection', return_value=self.connection)
        patcher.start()
        self.addCleanup(patcher.stop)
        sleeper = patch.object(collector.time, 'sleep')
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)

    def response(self, body, status=200):
        response = Mock(status=status, reason='fixture response')
        response.getheader.return_value = str(len(body))
        response.read.side_effect = io.BytesIO(body).read
        return response

    def saved(self, record):
        path = self.root / 'requests' / (record['request_id'] + '.json')
        self.assertEqual(json.loads(path.read_text()), record)
        return path

    def test_identical_polls_preserve_bytes_records_and_distinct_times(self):
        body = payload()
        self.connection.getresponse.side_effect = [self.response(body), self.response(body)]
        start = datetime(2026, 10, 1, 17, 35, 43, 123456, tzinfo=timezone.utc)
        def inspect_request(*args):
            records = []
            for path in self.root.glob('requests/*.json'):
                records.append(json.loads(path.read_text()))
            self.assertEqual(sum(record['outcome'] == 'started' for record in records), 1)
        self.connection.request.side_effect = inspect_request
        with patch.object(collector, 'datetime') as clock:
            clock.now.side_effect = [start + timedelta(seconds=i) for i in range(6)]
            results = collector.collect_vehicle_positions(self.url, self.root, 5, 2)
        self.assertEqual(len(results), 2)
        self.assertNotEqual(results[0]['request_id'], results[1]['request_id'])
        self.assertNotEqual(results[0]['received_at_utc'], results[1]['received_at_utc'])
        self.assertEqual(len(list(self.root.glob('payloads/*/response.pb'))), 1)
        self.sleep.assert_called_once_with(5)
        self.assertEqual(self.connection.request.call_count, 2)
        self.connection.request.assert_called_with('GET', '/VehiclePositions.pb?sample=1')
        for record in results:
            self.saved(record)
            self.assertTrue(record['valid_snapshot'])
            self.assertEqual(record['payload_sha256'], hashlib.sha256(body).hexdigest())
            self.assertEqual(Path(record['payload_path']).read_bytes(), body)
            self.assertEqual(record['feed_timestamp'], 1790876142)
            self.assertEqual(record['vehicle_timestamps'], [{'entity_id': 'entity-01', 'vehicle_timestamp': 1790876101}])
            self.assertNotEqual(record['request_started_at_utc'], record['received_at_utc'])
            self.assertEqual(datetime.fromisoformat(record['received_at_utc']).utcoffset(), timedelta(0))

    def test_absent_source_times_are_not_replaced_with_receipt_time(self):
        self.connection.getresponse.return_value = self.response(payload(False))
        record = collector.collect_vehicle_positions(self.url, self.root, 0, 1)[0]
        self.assertIsNone(record['feed_timestamp'])
        self.assertIsNone(record['vehicle_timestamps'][0]['vehicle_timestamp'])

    def test_timeout_has_no_payload_and_next_poll_still_runs(self):
        self.connection.request.side_effect = [TimeoutError('no bytes'), None]
        self.connection.getresponse.return_value = self.response(payload())
        failed, success = collector.collect_vehicle_positions(self.url, self.root, 0, 2)
        self.saved(failed)
        self.assertEqual(failed['outcome'], 'failed')
        self.assertIn('no bytes', failed['error'])
        self.assertNotIn('payload_sha256', failed)
        self.assertNotIn('received_at_utc', failed)
        self.assertFalse(failed['valid_snapshot'])
        self.assertTrue(success['valid_snapshot'])

    def test_complete_malformed_repeated_responses_keep_one_artifact(self):
        body = b'\xffmalformed'
        self.connection.getresponse.side_effect = [self.response(body), self.response(body)]
        results = collector.collect_vehicle_positions(self.url, self.root, 0, 2)
        self.assertNotEqual(results[0]['request_id'], results[1]['request_id'])
        for record in results:
            self.saved(record)
            self.assertFalse(record['valid_snapshot'])
            self.assertEqual(record['http_status'], 200)
            self.assertIn('DecodeError', record['error'])
            self.assertEqual(Path(record['payload_path']).read_bytes(), body)
        self.assertEqual(len(list(self.root.glob('payloads/*/response.pb'))), 1)

    def test_http_error_complete_body_is_failed_even_when_parseable(self):
        for body in (payload(), b'<html>unavailable</html>'):
            self.connection.getresponse.return_value = self.response(body, 503)
            record = collector.collect_vehicle_positions(self.url, self.root, 0, 1)[0]
            self.saved(record)
            self.assertEqual(record['outcome'], 'failed')
            self.assertFalse(record['valid_snapshot'])
            self.assertEqual(record['http_status'], 503)
            self.assertIn('HTTP 503', record['error'])
            self.assertEqual(record['payload_sha256'], hashlib.sha256(body).hexdigest())
            self.assertEqual(Path(record['payload_path']).read_bytes(), body)

    def test_empty_complete_response_is_retained_but_not_valid(self):
        self.connection.getresponse.return_value = self.response(b'')
        record = collector.collect_vehicle_positions(self.url, self.root, 0, 1)[0]
        self.assertEqual(record['outcome'], 'failed')
        self.assertFalse(record['valid_snapshot'])
        self.assertEqual(record['payload_sha256'], hashlib.sha256(b'').hexdigest())
        self.assertEqual(Path(record['payload_path']).read_bytes(), b'')

    def test_partial_read_and_short_content_length_have_no_payload_identity(self):
        for failure in ('timeout', 'incomplete', 'short'):
            with self.subTest(failure=failure):
                response = self.response(b'abc')
                if failure == 'timeout':
                    response.read.side_effect = [b'ab', TimeoutError('read timeout')]
                    size = 2
                elif failure == 'incomplete':
                    response.read.side_effect = [b'a', IncompleteRead(b'bc')]
                    size = 3
                else:
                    response.getheader.return_value = '10'
                    size = 3
                self.connection.getresponse.return_value = response
                record = collector.collect_vehicle_positions(self.url, self.root, 0, 1)[0]
                path = self.saved(record)
                self.assertEqual(record['outcome'], 'failed')
                self.assertEqual(record['partial_staging_size_bytes'], size)
                self.assertNotIn('payload_sha256', record)
                self.assertFalse(path.with_suffix('.part').exists())
        self.assertEqual(list(self.root.glob('payloads/*')), [])

    def test_restart_marks_started_records_and_discards_observed_partial(self):
        folder = self.root / 'requests'
        folder.mkdir(parents=True)
        started = {'request_id': 'old', 'request_url': self.url,
                   'request_started_at_utc': '2026-10-01T10:00:00+00:00',
                   'outcome': 'started', 'valid_snapshot': False}
        path = folder / 'old.json'
        path.write_text(json.dumps(started))
        path.with_suffix('.part').write_bytes(b'partial')
        self.connection.getresponse.return_value = self.response(payload())
        new = collector.collect_vehicle_positions(self.url, self.root, 0, 1)[0]
        recovered = json.loads(path.read_text())
        self.assertEqual(recovered['request_id'], 'old')
        self.assertEqual(recovered['request_started_at_utc'], started['request_started_at_utc'])
        self.assertEqual(recovered['outcome'], 'interrupted')
        self.assertEqual(recovered['response_outcome'], 'unknown')
        self.assertTrue(recovered['partial_staging_existed'])
        self.assertEqual(recovered['partial_staging_size_bytes'], 7)
        self.assertIn('interrupted_at_utc', recovered)
        self.assertNotIn('payload_sha256', recovered)
        self.assertFalse(path.with_suffix('.part').exists())
        self.assertNotEqual(new['request_id'], 'old')
        collector.collect_vehicle_positions(self.url, self.root, 0, 0)
        self.assertEqual(json.loads(path.read_text()), recovered)
        self.saved(new)

    def test_restart_without_staging_preserves_existing_complete_link(self):
        folder = self.root / 'requests'
        folder.mkdir(parents=True)
        prior = {'request_id': 'old', 'outcome': 'started',
                 'request_started_at_utc': '2026-10-01T10:00:00+00:00',
                 'payload_sha256': hashlib.sha256(payload()).hexdigest(), 'valid_snapshot': True}
        path = folder / 'old.json'
        path.write_text(json.dumps(prior))
        collector.collect_vehicle_positions(self.url, self.root, 0, 0)
        result = json.loads(path.read_text())
        self.assertEqual(result['outcome'], 'interrupted')
        self.assertFalse(result['partial_staging_existed'])
        self.assertEqual(result['partial_staging_size_bytes'], 0)
        self.assertEqual(result['payload_sha256'], prior['payload_sha256'])
        self.connection.request.assert_not_called()

    def test_process_interruption_is_reconciled_on_next_start(self):
        response = self.response(b'abc')
        response.read.side_effect = [b'ab', KeyboardInterrupt()]
        self.connection.getresponse.return_value = response
        with self.assertRaises(KeyboardInterrupt):
            collector.collect_vehicle_positions(self.url, self.root, 0, 1)
        path = next(self.root.glob('requests/*.json'))
        self.assertEqual(json.loads(path.read_text())['outcome'], 'started')
        self.assertEqual(path.with_suffix('.part').read_bytes(), b'ab')
        collector.collect_vehicle_positions(self.url, self.root, 0, 0)
        self.assertEqual(json.loads(path.read_text())['partial_staging_size_bytes'], 2)
        self.assertFalse(path.with_suffix('.part').exists())

    def test_invalid_poll_configuration_does_not_request(self):
        for interval, polls in ((-1, 1), (float('inf'), 1), (0, -1), (0, 1.5)):
            with self.assertRaises(ValueError):
                collector.collect_vehicle_positions(self.url, self.root, interval, polls)
        self.connection.request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
