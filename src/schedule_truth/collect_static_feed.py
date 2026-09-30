"""One static-feed request per call; callers decide when to retry."""

from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection, HTTPSConnection, HTTPException, IncompleteRead
import io
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
import zipfile
import zlib

from schedule_truth.archive_schedule import archive_schedule_zip


def collect_static_feed(url: str, archive_root: Path, timeout: float = 30) -> dict:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("A complete HTTP or HTTPS feed URL is required.")

    attempt_id = uuid4().hex
    attempt_path = archive_root / "attempts" / f"{attempt_id}.json"
    attempt_path.parent.mkdir(parents=True, exist_ok=True)
    res = {}
    res['attempt_id'] = attempt_id
    res['request_url'] = url
    res['attempted_at_utc'] = datetime.now(timezone.utc).isoformat()
    res['outcome'] = 'started'
    with attempt_path.open('x', encoding='utf-8') as file:
        json.dump(res, file, indent=4)

    body = bytearray()
    request_error = None
    connection = None
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
        while True:
            try:
                chunk = response.read(65536)
            except IncompleteRead as error:
                body.extend(error.partial)
                raise
            if not chunk:
                break
            body.extend(chunk)
        if response.status < 200 or response.status >= 300:
            request_error = f"HTTP {response.status}: {response.reason}"
    except (OSError, HTTPException) as error:
        request_error = f"{type(error).__name__}: {error}"
    finally:
        if connection is not None:
            connection.close()

    received_at_utc = datetime.now(timezone.utc)
    if not body:
        res['outcome'] = 'failed'
        res['error'] = request_error or 'No response bytes received'
    else:
        # Preserve received bytes before validation or archive metadata processing.
        download_path = attempt_path.with_suffix('.download')
        with download_path.open('xb') as file:
            file.write(body)
        zip_sha256 = hashlib.sha256(body).hexdigest()
        res['zip_sha256'] = zip_sha256
        validation_error = None
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                bad_member = archive.testzip()
                if bad_member is not None:
                    raise zipfile.BadZipFile(f"Bad CRC for member {bad_member!r}")
        except (zipfile.BadZipFile, EOFError, zlib.error, NotImplementedError, RuntimeError) as error:
            validation_error = f"{type(error).__name__}: {error}"

        if validation_error is not None:
            retained_path = archive_root / zip_sha256 / 'original.zip'
            retained_path.parent.mkdir(parents=True, exist_ok=True)
            if not retained_path.exists():
                with retained_path.open('xb') as file:
                    file.write(body)
            res['outcome'] = 'invalid_zip'
            res['zip_path'] = str(retained_path)
            res['error'] = validation_error
            if request_error is not None:
                res['request_error'] = request_error
        elif request_error is not None:
            # A readable ZIP does not override a failed request.
            res['outcome'] = 'failed'
            res['zip_path'] = str(download_path)
            res['error'] = request_error
        else:
            result = archive_schedule_zip(download_path, archive_root, received_at_utc)
            res['outcome'] = 'archived'
            res['zip_path'] = str(result['content']['zip_path'])
            res['receipt_id'] = result['receipt']['receipt_id']
            res['downloaded_at_utc'] = received_at_utc.isoformat()

    res['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    # Replace only this attempt's record; other attempts remain independent.
    finished_path = attempt_path.with_suffix('.json.tmp')
    with finished_path.open('x', encoding='utf-8') as file:
        json.dump(res, file, indent=4)
    finished_path.replace(attempt_path)
    if body and res['outcome'] in ('invalid_zip', 'archived'):
        download_path.unlink()
    return res
