"""Persist one complete Service Alerts response without interpreting its periods."""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import time
from uuid import uuid4

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from schedule_truth.collect_vehicle_positions import _save_request, _receive_with_deadline


def persist_alerts_response(
    archive_root: Path,
    request_id: str,
    body: bytes,
    http_status: int,
    request_started_at_utc: datetime,
    received_at_utc: datetime,
) -> dict:
    """Save exact Alerts bytes and request evidence, verifying replays without interpreting alert periods."""
    digest = hashlib.sha256(body).hexdigest()
    if not request_id or Path(request_id).name != request_id or '/' in request_id or '\\' in request_id:
        raise ValueError('request_id must be a filename component.')
    for value in (request_started_at_utc, received_at_utc):
        if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise ValueError('Request and receipt times must be aware UTC datetimes.')

    record_path = archive_root / 'requests' / f'{request_id}.json'
    record = None
    if record_path.exists():
        with record_path.open(encoding='utf-8') as file:
            record = json.load(file)

    evidence = {
        'request_id': request_id,
        'feed_type': 'service_alerts',
        'payload_sha256': digest,
        'http_status': http_status,
        'request_started_at_utc': request_started_at_utc.isoformat(),
        'received_at_utc': received_at_utc.isoformat(),
    }
    if record is not None:
        for field, value in evidence.items():
            if field in record and record[field] != value:
                raise ValueError(f'Conflicting {field} for request {request_id}')
        if record['outcome'] != 'started' and 'payload_sha256' not in record:
            raise ValueError(f'Terminal request without payload cannot be completed: {request_id}')
        if record['outcome'] != 'started':
            for field in evidence:
                if field not in record:
                    raise ValueError(f'Missing {field} in terminal request {request_id}')

    payload_path = archive_root / 'payloads' / digest / 'response.pb'
    if record is not None and record['outcome'] != 'started':
        if record.get('payload_path') != str(payload_path):
            raise ValueError(f'Conflicting payload link for request {request_id}')
    if payload_path.exists():
        if hashlib.sha256(payload_path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Payload integrity mismatch: {payload_path}')
    else:
        if record is not None and record['outcome'] != 'started':
            raise ValueError(f'Missing terminal payload: {payload_path}')
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = payload_path.with_name(uuid4().hex + '.tmp')
        with temporary.open('xb') as file:
            file.write(body)
        temporary.replace(payload_path)
    if record is not None and record['outcome'] != 'started':
        return record

    res = record.copy() if record is not None else {}
    res.update(evidence)
    res['payload_path'] = str(payload_path)
    res['size_bytes'] = len(body)
    res['valid_snapshot'] = False
    if http_status < 200 or http_status >= 300:
        res['outcome'] = 'failed'
        res['error'] = f'HTTP {http_status}'
    else:
        feed = gtfs_realtime_pb2.FeedMessage()
        try:
            feed.ParseFromString(body)
            if not feed.IsInitialized():
                raise DecodeError('Missing required Protobuf fields: ' + ', '.join(feed.FindInitializationErrors()))
        except DecodeError as error:
            res['outcome'] = 'failed'
            res['error'] = f'DecodeError: {error}'
        else:
            res['outcome'] = 'received'
            res['valid_snapshot'] = True
            res['feed_timestamp'] = feed.header.timestamp if feed.header.HasField('timestamp') else None
    res['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    record_path.parent.mkdir(parents=True, exist_ok=True)
    _save_request(record_path, res)
    return res


def poll_alerts(url, root, timeout=30, max_response_bytes=10 * 1024 * 1024,
                      request_deadline_seconds=120):
    """Persist one deadline-limited poll and its outcome; the caller must hold archive ownership."""
    request_id = uuid4().hex
    path = root / 'requests' / f'{request_id}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix('.part')
    started_monotonic = time.monotonic()
    started = datetime.now(timezone.utc)
    res = {}
    res['request_id'] = request_id
    res['feed_type'] = 'service_alerts'
    res['request_url'] = url
    res['request_started_at_utc'] = started.isoformat()
    res['request_deadline_seconds'] = request_deadline_seconds
    res['outcome'] = 'started'
    res['valid_snapshot'] = False
    _save_request(path, res)
    transfer = _receive_with_deadline(url, staging, timeout, max_response_bytes,
                                      started_monotonic + request_deadline_seconds)
    if transfer['complete']:
        res = persist_alerts_response(root, request_id, staging.read_bytes(),
                                            transfer['http_status'], started,
                                            datetime.fromisoformat(transfer['received_at_utc']))
    else:
        for field in ('http_status', 'observed_size_bytes'):
            if field in transfer:
                res[field] = transfer[field]
        res['outcome'] = 'failed'
        res['error'] = transfer['request_error']
        res['partial_staging_existed'] = staging.exists()
        res['partial_staging_size_bytes'] = staging.stat().st_size if staging.exists() else 0
        if res['error'] == 'request_deadline_exceeded':
            res['observed_size_bytes'] = res['partial_staging_size_bytes']
        res['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        _save_request(path, res)
    staging.unlink(missing_ok=True)
    return res
