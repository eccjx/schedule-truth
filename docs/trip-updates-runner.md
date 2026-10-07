# Trip Updates collection

Use a dedicated archive root on Windows. Install requirements.txt, then run from the repository root:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -B -m schedule_truth.run_trip_updates --url https://cdn.mbta.com/realtime/TripUpdates.pb --root data/raw/trip_updates --interval-seconds 30 --timeout 30 --request-deadline-seconds 120 --max-response-bytes 10485760
```

The runner acquires the existing root ownership guard before checking histories or reconciling started requests. It rejects roots with non-Trip-Updates request records. Recovery, killable network reception, 120-second monotonic deadline, 10 MiB size limit, and signal-driven graceful shutdown reuse the Vehicle Positions mechanics. Completion-to-next-start cadence defaults to 30 seconds, including after failed polls. No history list is accumulated.

Every request has `feed_type: trip_updates`, source URL, distinct request identity and UTC collection times. Complete bytes are kept at `payloads/<sha256>/response.pb`; records are at `requests/<id>.json`. Existing hash-named payloads are verified before reuse. Complete malformed or HTTP-error responses remain failed byte evidence. Incomplete transfers have no payload identity.

New request JSON contains collection metadata, status/error, payload hash/path/size, and small scalar diagnostics. A successfully decoded feed retains its header timestamp as `feed_timestamp` (null if absent). Per-trip and per-stop arrays are not embedded. Decode the unchanged `response.pb` with `gtfs_realtime_pb2.FeedMessage` to read TripUpdate timestamps and stop arrival/departure source times, using `HasField` to distinguish missing values from Protobuf defaults. These source times remain distinct from local collection times and are not confirmed actual stop events. Record size no longer grows with the number of trip/stop summaries; path and error-text lengths can still vary. Historical expanded records remain unchanged, including during identical replay.

`persist_trip_updates_response` is a complete-response persistence function. Call it while owning the dedicated root, as the runner does. A started request can be completed if its recorded evidence agrees. Identical complete-evidence replay returns the existing terminal record without rewriting either file. Conflicting bytes, HTTP status, request-start or receipt time are rejected before new payload writes. A corrupt or missing terminal payload is an integrity error, not automatic repair. Payload creation/verification precedes final request linkage. An interrupted write can leave an unlinked payload; general orphan repair is not implemented.

The total network deadline does not bound every Windows/storage operation or post-reception parsing. The existing cleanup, disk-failure, dependency installation, cross-machine ownership, and live-soak limitations remain. No feed-health, missing-trip, or stop-event truth inference is performed.
