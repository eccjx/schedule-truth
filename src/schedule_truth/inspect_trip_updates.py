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
    """Verify saved payload bytes and return one unambiguous trip/stop match without claiming actual events."""
    record_path = archive_root / "requests" / f"{request_id}.json"
    if not record_path.exists():
        raise FileNotFoundError(f"Request record not found: {record_path}")
    with record_path.open(encoding='utf-8') as file:
        record = json.load(file)

    if record["feed_type"] != "trip_updates":
        raise ValueError(f"Not a Trip Updates request: {request_id}")
    if "payload_sha256" not in record:
        raise ValueError(f"Request has no complete payload: {request_id}")
    if record.get("valid_snapshot") is not True:
        raise ValueError(f"Request is not a valid Trip Updates snapshot: {request_id}")

    payload_sha256 = record["payload_sha256"]
    payload_path = archive_root / "payloads" / payload_sha256 / "response.pb"
    if not payload_path.exists():
        raise FileNotFoundError(f"Payload not found: {payload_path}")
    body = payload_path.read_bytes()
    if hashlib.sha256(body).hexdigest() != payload_sha256:
        raise ValueError(f"Payload hash mismatch: {payload_path}")

    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(body)
    except DecodeError as error:
        raise ValueError(f"Invalid Trip Updates payload: {payload_path}") from error
    if not feed.IsInitialized():
        raise ValueError(f"Incomplete Trip Updates payload: {payload_path}")

    matches = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        update = entity.trip_update
        if not update.trip.HasField("trip_id") or update.trip.trip_id != trip_id:
            continue
        for stop in update.stop_time_update:
            if stop.HasField("stop_sequence") and stop.stop_sequence == stop_sequence:
                matches.append((update, stop))

    if not matches:
        raise LookupError(f"Trip {trip_id}, stop sequence {stop_sequence} not found")
    if len(matches) > 1:
        raise ValueError(f"Ambiguous trip {trip_id}, stop sequence {stop_sequence}")

    update, stop = matches[0]
    return {
        "request_id": request_id,
        "payload_sha256": payload_sha256,
        "trip_id": trip_id,
        "trip_start_date": update.trip.start_date if update.trip.HasField("start_date") else None,
        "stop_sequence": stop_sequence,
        "stop_id": stop.stop_id if stop.HasField("stop_id") else None,
        "arrival_time": stop.arrival.time if stop.HasField("arrival") and stop.arrival.HasField("time") else None,
        "departure_time": stop.departure.time if stop.HasField("departure") and stop.departure.HasField("time") else None,
        "trip_update_timestamp": update.timestamp if update.HasField("timestamp") else None,
        "feed_timestamp": feed.header.timestamp if feed.header.HasField("timestamp") else None,
        "received_at_utc": record["received_at_utc"],
    }
