# Trip Updates first collection slice

Status: author-accepted Trip Updates collector/runner slice, 2026-10-07. The compact-record revision, independent tests, one live persisted poll, and independent review support this bounded acceptance. Source and tests remain uncommitted in the working tree. This is not Phase 2 milestone acceptance.

## Observed sample

The MBTA static feed's `linked_datasets.txt` points to `https://cdn.mbta.com/realtime/TripUpdates.pb`. One ad hoc response saved under ignored `data/raw/trip_updates_probe/sample.pb` contained 942,790 bytes, 1,595 entities, and SHA-256 `1b889f5741c031903bdddb8531304895f04226ce47f5c6249bbe17ab428cf183`. This probe did not record precise request-start and receipt timestamps, so its file modification time is not collection evidence.

One entity (`78258766`) described trip `78258766` with `start_date=20261002`. Its `TripUpdate.timestamp` was 2026-10-02 22:29:19 UTC; the feed header timestamp was 22:29:29 UTC. Its first stop (`stop_sequence=1`, `stop_id=65`) supplied a departure `StopTimeEvent.time` of 23:05:00 UTC. That future departure is a prediction in this sample, not an observed departure.

## Time meanings

- Preserve the stop arrival/departure `StopTimeEvent.time` as a source-provided event time. A Trip Update can contain future predictions and past stop times. Collection does not label a stop time as a confirmed actual event merely because its value is in the past.
- Preserve `TripUpdate.timestamp` as the source's time for the trip update and `FeedHeader.timestamp` as feed creation time. Neither is a vehicle measurement or stop event time.
- Record aware-UTC local request start, receipt when a complete body arrives, and failure/finish times separately. Never replace an absent source timestamp with the collector's clock without an explicit later rule.
- Classification of past stop times, confidence, and stop-event reconstruction belong to later analysis, not raw collection.

## Payload, request, and failure identity

- Hash the exact complete HTTP response bytes with SHA-256. Identical bytes across polls share one immutable payload content identity; each poll retains its own request ID, HTTP result, and timestamps, linked to that payload when complete.
- Reuse the Vehicle Positions first-slice failure rules: a no-byte timeout retains a failed request with no payload; a complete malformed Protobuf body or complete HTTP-error body remains exact-byte failed evidence and never becomes a valid Trip Updates snapshot.
- After a restart, a prior `started` request is marked `interrupted` with its outcome unknown. Record whether partial staging existed and its observed byte count, discard those incomplete bytes, and begin the next poll under a new request ID. No payload identity or valid snapshot is formed from partial bytes.
- Request IDs identify individual polls and terminal outcomes are immutable. A later complete response cannot reuse a request ID already recorded as timed out, interrupted, or otherwise terminal without a complete payload; reject it without writing. A new poll gets a new ID. An exact replay of an already completed response may return the existing record only when its bytes, HTTP status, and recorded request/receipt evidence match. Conflicting evidence under the same ID is an error.
- Keep each request JSON compact: request ID, feed label, source URL, UTC request/receipt/finish times, HTTP status, outcome/error, payload hash/path/size when complete, and small scalar diagnostics such as the feed-header timestamp when available. Do not embed per-trip or per-stop arrays in every request record. Decode trip and stop values from the immutable Protobuf when a later analysis or audit needs them; preserve missing source fields as missing rather than substituting collection time.
- Missing Trip Updates for a trip do not prove that the trip ran on time or did not run. A syntactically valid response does not establish freshness or truth of its predictions.

## First runner integration

- Poll sequentially, starting immediately after startup reconciliation and then 30 seconds after the previous request finishes, whether it succeeded or failed. The completion-to-next-start interval is configurable. Do not overlap polls or add a separate rapid retry/backoff rule in this first slice.
- Use a configurable 10 MiB (10 * 1024 * 1024 bytes) maximum response body and a configurable 120-second monotonic deadline from request start for network reception. Reuse the accepted Vehicle Positions rules for oversized and deadline-expired responses: persist a failed request with reason and observed partial byte count, discard incomplete staging, and create no payload identity or valid snapshot. Graceful stop retains the active request's original deadline. The deadline does not guarantee an exact process exit time because cleanup and storage can continue afterward.
- Persist `feed_type: trip_updates` on every request record. This names the configured feed being polled, not a claim that every entity in the returned Protobuf is a Trip Update. Preserve the source URL and exact bytes. A syntactically initialized Protobuf is not by itself a freshness, completeness, or service-health assertion.
- Use a dedicated Trip Updates archive root with its own single-writer ownership guard, request records, transient staging files, and immutable payloads under exact-byte SHA-256. Another writer for that same root must fail before reconciliation or writing; the Vehicle Positions root may be polled independently. Do not mix the two feeds' request histories merely because payload hashes might match.
- Adapt the existing Windows transport, deadline, storage, recovery, and runner mechanics where practical. The author approved the same behavior, not a specific refactor. Keep Trip Updates source timestamps and stop-event values distinct from local request/receipt time, and do not classify predictions as actual arrivals or departures during raw collection.

## Still open

Clean-install verification, sustained live continuous evidence, cross-feed operations, content-type validation beyond syntactic Protobuf, feed-health conclusions, and eventual stop-event reconstruction remain follow-ups. The ad hoc sample above is illustrative; a separate October 5 live persisted poll verified exact bytes, request/receipt times, and source fields. The compact-record revision was measured from those retained live bytes in a temporary archive, not through a new live poll. Review and tests do not establish actual-stop-event truth, full process-exit deadlines, or general crash recovery.

Reference: [GTFS Realtime Trip Updates](https://gtfs.org/documentation/realtime/feed-entities/trip-updates/) and [reference fields](https://gtfs.org/documentation/realtime/reference/).
