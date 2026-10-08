from pathlib import Path
import json
import hashlib

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

def inspect_trip_stop(
    archive_root: Path,
    request_id: str,
    trip_id: str,
    stop_sequence: int,
) -> dict:
    record_path = archive_root / "requests" / f"{request_id}.json"
    if not record_path.exists():
        raise FileNotFoundError(f"Request record not found: {record_path}")
    with record_path.open(encoding='utf-8') as file:
        record = json.load(file)

    if record["feed_type"] != "trip_updates":
        raise ValueError(f"Not a Trip Updates request: {request_id}")
    if "payload_sha256" not in record:
        raise ValueError(f"Request has no complete payload: {request_id}")

    payload_sha256 = record["payload_sha256"]
    payload_path = archive_root / "payloads" / payload_sha256 / "response.pb"
    if not payload_path.exists():
        raise FileNotFoundError(f"Payload not found: {payload_path}")
    body = payload_path.read_bytes()
    if hashlib.sha256(body).hexdigest() != payload_sha256:
        raise ValueError(f"Payload hash mismatch: {payload_path}")
