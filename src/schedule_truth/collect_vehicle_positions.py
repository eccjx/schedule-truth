"""Finite Vehicle Positions polling; raw source timestamps are Unix seconds."""

import argparse
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection, HTTPSConnection, HTTPException, IncompleteRead
import json
import math
from pathlib import Path
import time
from urllib.parse import urlsplit
from uuid import uuid4

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2


def _save_request(path: Path, record: dict):
    temporary = path.with_suffix('.json.tmp')
    with temporary.open('w', encoding='utf-8') as file:
        json.dump(record, file, indent=4)
    temporary.replace(path)


def recover_started_requests(root: Path):
    for path in (root / 'requests').glob('*.json'):
        with path.open(encoding='utf-8') as file:
            record = json.load(file)
        staging = path.with_suffix('.part')
        if record['outcome'] == 'started':
            record['outcome'] = 'interrupted'
            record['interrupted_at_utc'] = datetime.now(timezone.utc).isoformat()
            record['response_outcome'] = 'unknown'
            record['partial_staging_existed'] = staging.exists()
            record['partial_staging_size_bytes'] = staging.stat().st_size if staging.exists() else 0
            _save_request(path, record)
        # Repeat-safe if interrupted after recording recovery but before deletion.
        if record['outcome'] == 'interrupted' and record.get('partial_staging_existed'):
            staging.unlink(missing_ok=True)


def _poll_vehicle_positions(url: str, root: Path, timeout: float) -> dict:
    parts = urlsplit(url)
    request_id = uuid4().hex
    path = root / 'requests' / f'{request_id}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix('.part')
    res = {}
    res['request_id'] = request_id
    res['request_url'] = url
    res['request_started_at_utc'] = datetime.now(timezone.utc).isoformat()
    res['outcome'] = 'started'
    res['valid_snapshot'] = False
    _save_request(path, res)

    connection = None
    complete = False
    request_error = None
    try:
        if parts.scheme == 'https':
            connection = HTTPSConnection(parts.hostname, parts.port, timeout=timeout)
        else:
            connection = HTTPConnection(parts.hostname, parts.port, timeout=timeout)
        target = parts.path or '/'
        if parts.query:
            target += '?' + parts.query
        connection.request('GET', target)
        response = connection.getresponse()
        res['http_status'] = response.status
        expected_length = response.getheader('Content-Length')
        if expected_length is not None:
            try:
                expected_length = int(expected_length)
            except ValueError as error:
                raise HTTPException('Invalid Content-Length') from error
            if expected_length < 0:
                raise HTTPException('Negative Content-Length')
        received_size = 0
        with staging.open('xb') as file:
            while True:
                try:
                    chunk = response.read(65536)
                except IncompleteRead as error:
                    file.write(error.partial)
                    raise
                if not chunk:
                    break
                file.write(chunk)
                received_size += len(chunk)
            if expected_length is not None and received_size != expected_length:
                raise HTTPException(f'Incomplete response: expected {expected_length}, received {received_size} bytes')
        res['received_at_utc'] = datetime.now(timezone.utc).isoformat()
        complete = True
        if response.status < 200 or response.status >= 300:
            request_error = f'HTTP {response.status}: {response.reason}'
    except (OSError, HTTPException) as error:
        request_error = f'{type(error).__name__}: {error}'
    finally:
        if connection is not None:
            connection.close()

    if not complete:
        res['outcome'] = 'failed'
        res['error'] = request_error
        res['partial_staging_existed'] = staging.exists()
        res['partial_staging_size_bytes'] = staging.stat().st_size if staging.exists() else 0
    else:
        body = staging.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        payload = root / 'payloads' / digest / 'response.pb'
        payload.parent.mkdir(parents=True, exist_ok=True)
        if not payload.exists():
            staging.replace(payload)
        res['payload_sha256'] = digest
        res['payload_path'] = str(payload)
        res['size_bytes'] = len(body)
        if request_error is not None:
            res['outcome'] = 'failed'
            res['error'] = request_error
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
                res['vehicle_timestamps'] = []
                for entity in feed.entity:
                    if entity.HasField('vehicle'):
                        observation = {}
                        observation['entity_id'] = entity.id
                        observation['vehicle_timestamp'] = entity.vehicle.timestamp if entity.vehicle.HasField('timestamp') else None
                        res['vehicle_timestamps'].append(observation)

    res['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    _save_request(path, res)
    staging.unlink(missing_ok=True)
    return res


def collect_vehicle_positions(url: str, root: Path, interval_seconds: float, polls: int,
                              timeout: float = 30) -> list[dict]:
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError('A complete HTTP or HTTPS URL is required.')
    if type(polls) is not int or polls < 0:
        raise ValueError('polls must be a nonnegative integer.')
    if not math.isfinite(interval_seconds) or interval_seconds < 0:
        raise ValueError('interval_seconds must be finite and nonnegative.')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be finite and positive.')
    recover_started_requests(root)
    res = []
    for index in range(polls):
        if index > 0:
            time.sleep(interval_seconds)
        res.append(_poll_vehicle_positions(url, root, timeout))
    return res


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--interval-seconds', required=True, type=float)
    parser.add_argument('--polls', required=True, type=int)
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    results = collect_vehicle_positions(args.url, args.root, args.interval_seconds, args.polls, args.timeout)
    print(json.dumps(results, indent=4))
