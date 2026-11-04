# Service Alerts first collection contract

Status: author-approved operating/raw-evidence contract on 2026-11-02; bounded persistence, poll and Windows runner slice explicitly author accepted on 2026-11-04 after independent tests/review. Acceptance applies to current working-tree integration; Phase 2 as a whole remains unaccepted. Sustained live operation, clean installation and broader recovery are not established.

## Observed sample and time meanings

The MBTA static feed's `linked_datasets.txt` points to `https://cdn.mbta.com/realtime/Alerts.pb`. An ignored ad hoc sample contained 328,610 bytes, 147 entities, and SHA-256 `5096fff0bc5d14b935e6fae5a2af9cc86cc499f26fd63359ecd047ce3f1a2873`. Its feed-header timestamp was 2026-11-02 22:42:31 UTC. Alert `1001875` had multiple active periods, including 2026-11-02 23:00 to 2026-11-03 08:00 UTC; alert `1000001` had a start with no end. The probe did not record a precise collection receipt.

The feed timestamp is the source's feed-creation time. Local request start, complete receipt, and finish times are collection evidence. Alert `active_period` values are source display intervals, not receipt times or proof of exactly when a disruption occurred. Preserve missing period bounds and all periods in the unchanged Protobuf. Do not interpret an alert as proof of a particular vehicle or trip outcome during raw collection.

## Identity and outcomes

- Give every HTTP poll its own request ID and compact `feed_type: service_alerts` record. Hash exact complete response bytes with SHA-256; identical bytes may share one immutable payload while separate polls keep separate request/receipt evidence.
- A complete valid response links its payload and request record. Complete malformed Protobuf or HTTP-error bodies remain exact-byte failed evidence, not valid snapshots. Existing hash-named payloads are verified before reuse. Same-ID replay/conflicts and terminal no-payload immutability follow the approved Trip Updates persistence rules.
- An incomplete, timed-out, or oversized response records failure, finish time, and observed partial-byte count. Discard partial staging bytes; create no payload hash, immutable payload, or valid snapshot from incomplete bytes. Failure does not prove an alert or disruption is absent.
- On restart, mark an earlier `started` request `interrupted` with unknown response outcome and observed staged-byte count, discard partial staging, and give the next poll a new ID. Earlier completed records and payloads remain unchanged. This is bounded restart evidence, not general power-loss repair.

## Operating rules

- Use a dedicated Alerts archive root and a single-writer guard before reconciliation or writes. A second writer for that root fails clearly; the Vehicle Positions and Trip Updates roots can operate independently.
- Poll sequentially: one immediate poll after startup reconciliation, then wait a configurable 60 seconds after each poll finishes, whether it succeeded or failed. Do not overlap or add rapid retries in this slice.
- Default configurable limits: 10 MiB maximum HTTP body, 30-second socket inactivity timeout, and a 120-second monotonic deadline from request start for network reception. Graceful stop starts no new poll and does not reset the active request's original deadline. Process cleanup and storage can extend total exit time.
- Keep per-request JSON compact. A scalar feed-header timestamp may be recorded when present; alert periods and other per-alert details remain in exact raw bytes for later decoding.

## Concrete cases

| Case | Retained result |
| --- | --- |
| HTTP 200, complete initialized Protobuf | One request record linked to the exact-byte payload; feed and receipt timestamps remain separate. |
| Timeout after partial body | Failed request with partial-byte count; no payload identity or valid snapshot. |
| Crash during reception | Prior `started` record becomes `interrupted` on restart; next poll uses a new ID. |

The first slice does not establish clean installation, sustained live operation, cross-host ownership, general crash recovery, feed freshness, alert impact interpretation, or service-outcome truth.
