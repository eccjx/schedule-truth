"""Collector requests are mocked; archive writes and ZIP validation are real."""

from datetime import datetime, timedelta
import csv
import hashlib
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import sys
import struct
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from schedule_truth import collect_static_feed as collector
from schedule_truth.archive_schedule import load_schedule_snapshots


def feed_zip(coverage=True):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('agency.txt', 'agency_name,agency_timezone\nMBTA,America/New_York\n')
        if coverage:
            archive.writestr('feed_info.txt', 'feed_start_date,feed_end_date\n20260901,20260930\n')
    return buffer.getvalue()


class CollectStaticFeedTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'archive'
        self.url = 'https://example.test/MBTA_GTFS.zip?version=current'
        self.connection = Mock()
        patcher = patch.object(collector, 'HTTPSConnection', return_value=self.connection)
        patcher.start()
        self.addCleanup(patcher.stop)

    def response(self, body, status=200):
        response = Mock(status=status, reason='fixture response')
        response.read.side_effect = io.BytesIO(body).read
        self.connection.getresponse.return_value = response
        return response

    def assert_saved(self, result):
        path = self.root / 'attempts' / (result['attempt_id'] + '.json')
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), result)
        for key in ('attempted_at_utc', 'finished_at_utc'):
            self.assertEqual(datetime.fromisoformat(result[key]).utcoffset(), timedelta(0))

    def assert_no_receipt(self):
        self.assertEqual(list(self.root.glob('receipts/*.json')), [])
        self.assertEqual(list(self.root.glob('*/content.json')), [])
        self.assertEqual(load_schedule_snapshots(self.root), [])

    def test_attempt_is_persisted_before_request_and_valid_zip_links_receipt(self):
        body = feed_zip()
        self.response(body)
        def inspect_request(*args):
            paths = list((self.root / 'attempts').glob('*.json'))
            self.assertEqual(len(paths), 1)
            record = json.loads(paths[0].read_text(encoding='utf-8'))
            self.assertEqual(record['outcome'], 'started')
            self.assertEqual(record['request_url'], self.url)
            self.assertEqual(record['attempt_id'], paths[0].stem)
            self.assertEqual(datetime.fromisoformat(record['attempted_at_utc']).utcoffset(), timedelta(0))
        self.connection.request.side_effect = inspect_request
        result = collector.collect_static_feed(self.url, self.root)
        self.assert_saved(result)
        self.connection.request.assert_called_once_with('GET', '/MBTA_GTFS.zip?version=current')
        self.assertEqual(result['outcome'], 'archived')
        self.assertEqual(result['zip_sha256'], hashlib.sha256(body).hexdigest())
        self.assertEqual(Path(result['zip_path']).read_bytes(), body)
        receipt = json.loads((self.root / 'receipts' / (result['receipt_id'] + '.json')).read_text())
        self.assertEqual(receipt['zip_sha256'], result['zip_sha256'])
        self.assertEqual(receipt['downloaded_at_utc'], result['downloaded_at_utc'])
        self.assertEqual(len(load_schedule_snapshots(self.root)), 1)

    def test_no_bytes_failure_and_caller_retry_have_separate_attempts(self):
        self.connection.request.side_effect = TimeoutError('timed out')
        failed = collector.collect_static_feed(self.url, self.root)
        self.assert_saved(failed)
        self.assertEqual(failed['outcome'], 'failed')
        self.assertIn('timed out', failed['error'])
        self.assertNotIn('zip_sha256', failed)
        self.assertNotIn('receipt_id', failed)
        self.assert_no_receipt()
        self.connection.request.side_effect = None
        self.response(feed_zip())
        successful = collector.collect_static_feed(self.url, self.root)
        self.assertNotEqual(failed['attempt_id'], successful['attempt_id'])
        self.assertEqual(self.connection.request.call_count, 2)
        self.assertEqual(len(list(self.root.glob('attempts/*.json'))), 2)
        self.assert_saved(failed)
        self.assert_saved(successful)

    def test_identical_successful_downloads_have_distinct_attempts_and_receipts(self):
        body = feed_zip()
        self.response(body)
        first = collector.collect_static_feed(self.url, self.root)
        self.response(body)
        second = collector.collect_static_feed(self.url, self.root)
        self.assertNotEqual(first['attempt_id'], second['attempt_id'])
        self.assertNotEqual(first['receipt_id'], second['receipt_id'])
        self.assertEqual(first['zip_sha256'], second['zip_sha256'])
        self.assertEqual(len(list(self.root.glob('*/original.zip'))), 1)
        self.assertEqual(len(load_schedule_snapshots(self.root)), 2)

    def test_invalid_zip_and_http_error_body_are_retained_without_receipts(self):
        body = b'<html>unavailable</html>\x00\xff'
        for status in (200, 503):
            self.response(body, status)
            result = collector.collect_static_feed(self.url, self.root)
            self.assert_saved(result)
            self.assertEqual(result['outcome'], 'invalid_zip')
            self.assertTrue(result['error'])
            self.assertEqual(result['zip_sha256'], hashlib.sha256(body).hexdigest())
            self.assertEqual(Path(result['zip_path']).read_bytes(), body)
            self.assertNotIn('receipt_id', result)
            self.assert_no_receipt()

    def test_empty_response_has_error_but_no_content(self):
        self.response(b'')
        result = collector.collect_static_feed(self.url, self.root)
        self.assert_saved(result)
        self.assertEqual(result['outcome'], 'failed')
        self.assertNotIn('zip_sha256', result)
        self.assert_no_receipt()

    def test_redirect_is_not_followed_and_failed_http_zip_is_failed(self):
        body = feed_zip()
        self.response(body, 302)
        result = collector.collect_static_feed(self.url, self.root)
        self.connection.request.assert_called_once()
        self.assert_saved(result)
        self.assertEqual(result['outcome'], 'failed')
        self.assertIn('HTTP 302', result['error'])
        self.assertEqual(Path(result['zip_path']).read_bytes(), body)
        self.assert_no_receipt()

    def test_readable_zip_with_http_or_transport_error_keeps_failed_evidence(self):
        body = feed_zip()
        for failure in ('http', 'transport'):
            with self.subTest(failure=failure):
                if failure == 'http':
                    self.response(body, 503)
                    expected_error = 'HTTP 503: fixture response'
                else:
                    response = self.response(b'')
                    response.read.side_effect = [body, TimeoutError('read timed out')]
                    expected_error = 'TimeoutError: read timed out'
                result = collector.collect_static_feed(self.url, self.root)
                self.assert_saved(result)
                self.assertEqual(result['outcome'], 'failed')
                self.assertEqual(result['error'], expected_error)
                self.assertEqual(result['zip_sha256'], hashlib.sha256(body).hexdigest())
                staged = self.root / 'attempts' / (result['attempt_id'] + '.download')
                self.assertEqual(Path(result['zip_path']), staged)
                self.assertEqual(staged.read_bytes(), body)
                self.assertNotIn('receipt_id', result)
                self.assert_no_receipt()

    def test_initial_persistence_failure_prevents_request(self):
        with patch.object(collector.json, 'dump', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                collector.collect_static_feed(self.url, self.root)
        self.connection.request.assert_not_called()

    def test_partial_bytes_survive_read_failure(self):
        response = self.response(b'')
        response.read.side_effect = [b'PK', IncompleteRead(b'partial')]
        result = collector.collect_static_feed(self.url, self.root)
        self.assert_saved(result)
        self.assertEqual(Path(result['zip_path']).read_bytes(), b'PKpartial')
        self.assertIn('IncompleteRead', result['request_error'])
        self.assertEqual(result['outcome'], 'invalid_zip')
        self.assert_no_receipt()

    def test_crc_damaged_zip_is_not_selectable(self):
        body = feed_zip()
        body = body.replace(b'MBTA,America', b'XETA,America')
        self.response(body)
        result = collector.collect_static_feed(self.url, self.root)
        self.assertEqual(result['outcome'], 'invalid_zip')
        self.assertIn('CRC', result['error'])
        self.assertEqual(Path(result['zip_path']).read_bytes(), body)
        self.assert_no_receipt()

    def test_unsupported_and_encrypted_zip_finish_with_validation_evidence(self):
        for kind, exception in (('unsupported', NotImplementedError), ('encrypted', RuntimeError)):
            with self.subTest(kind=kind):
                body = bytearray(feed_zip())
                local = body.index(b'PK\x03\x04')
                central = body.index(b'PK\x01\x02')
                if kind == 'encrypted':
                    struct.pack_into('<H', body, local + 6, 1)
                    struct.pack_into('<H', body, central + 8, 1)
                else:
                    struct.pack_into('<H', body, local + 8, 99)
                    struct.pack_into('<H', body, central + 10, 99)
                body = bytes(body)
                with zipfile.ZipFile(io.BytesIO(body)) as archive:
                    with self.assertRaises(exception) as caught:
                        archive.testzip()
                self.response(body, 503)
                result = collector.collect_static_feed(self.url, self.root)
                self.assert_saved(result)
                self.assertEqual(result['outcome'], 'invalid_zip')
                self.assertEqual(result['http_status'], 503)
                self.assertEqual(result['request_error'], 'HTTP 503: fixture response')
                self.assertEqual(result['error'], f'{exception.__name__}: {caught.exception}')
                digest = hashlib.sha256(body).hexdigest()
                self.assertEqual(result['zip_sha256'], digest)
                self.assertEqual(Path(result['zip_path']), self.root / digest / 'original.zip')
                self.assertEqual(Path(result['zip_path']).read_bytes(), body)
                self.assertNotIn('receipt_id', result)
                self.assert_no_receipt()

    def test_oversized_coverage_finishes_attempt_with_unknown_coverage_receipt(self):
        buffer = io.BytesIO()
        oversized = '9' * (csv.field_size_limit() + 1)
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('feed_info.txt', f'feed_start_date,feed_end_date\n{oversized},20260930\n')
            archive.writestr('agency.txt', 'agency_name,agency_timezone\nMBTA,America/New_York\n')
        body = buffer.getvalue()
        self.response(body, 200)
        result = collector.collect_static_feed(self.url, self.root)
        self.assert_saved(result)
        self.assertEqual(result['outcome'], 'archived')
        self.assertEqual(result['http_status'], 200)
        self.assertEqual(result['zip_sha256'], hashlib.sha256(body).hexdigest())
        self.assertEqual(Path(result['zip_path']).read_bytes(), body)
        content = json.loads((Path(result['zip_path']).parent / 'content.json').read_text())
        self.assertIsNone(content['feed_start_date'])
        self.assertIsNone(content['feed_end_date'])
        self.assertIn('field larger than field limit', content['coverage_error'])
        receipt = json.loads((self.root / 'receipts' / (result['receipt_id'] + '.json')).read_text())
        self.assertEqual(receipt['zip_sha256'], result['zip_sha256'])
        self.assertEqual(receipt['downloaded_at_utc'], result['downloaded_at_utc'])
        self.assertEqual(len(load_schedule_snapshots(self.root)), 1)

    def test_unknown_coverage_keeps_existing_archive_behavior(self):
        self.response(feed_zip(coverage=False))
        result = collector.collect_static_feed(self.url, self.root)
        self.assertEqual(result['outcome'], 'archived')
        snapshot = load_schedule_snapshots(self.root)[0]
        self.assertIsNone(snapshot['feed_start_date'])
        self.assertIsNone(snapshot['feed_end_date'])
        self.assertTrue(snapshot['coverage_error'])

    def test_archive_error_leaves_started_attempt_and_download_for_investigation(self):
        body = feed_zip()
        self.response(body)
        with patch.object(collector, 'archive_schedule_zip', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                collector.collect_static_feed(self.url, self.root)
        path = next(self.root.glob('attempts/*.json'))
        self.assertEqual(json.loads(path.read_text())['outcome'], 'started')
        self.assertEqual(path.with_suffix('.download').read_bytes(), body)
        self.assert_no_receipt()


if __name__ == '__main__':
    unittest.main()
