# Trip Updates first collection slice

Status: author-approved collection semantics, 2026-10-02. No Trip Updates collector or independent tests yet.

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
- Missing Trip Updates for a trip do not prove that the trip ran on time or did not run. A syntactically valid response does not establish freshness or truth of its predictions.

## Still open

The roadmap suggests approximately 30-second polling for Trip Updates, but the author has not approved a production cadence or runner contract for this feed. Size bounds, single-writer coordination across feeds, exact integration with the Vehicle Positions runner, and clean-install verification remain implementation/design follow-ups. The observed sample is illustrative, not a live collector acceptance test.

Reference: [GTFS Realtime Trip Updates](https://gtfs.org/documentation/realtime/feed-entities/trip-updates/) and [reference fields](https://gtfs.org/documentation/realtime/reference/).
