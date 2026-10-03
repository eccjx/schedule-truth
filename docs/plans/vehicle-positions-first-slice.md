# Vehicle Positions first collection slice

Status: author-approved contract, 2026-10-01. A finite Vehicle Positions collector implements this bounded slice and passed independent tests and review; Phase 2 as a whole is not accepted.

## Observed sample

One raw MBTA Vehicle Positions protobuf response was saved locally on 2026-10-01. It contained 70,667 bytes, 630 vehicle entities, and SHA-256 `3cb63cc81a4591dcf9a40db2c3b491b7c45225e96c214c3febf939fcf5ebbe65`. The collector request began at `2026-10-01T17:35:43.732571+00:00` and finished receiving at `2026-10-01T17:35:44.126178+00:00`. The feed header timestamp was `2026-10-01T17:35:42+00:00`; one vehicle position timestamp was `2026-10-01T17:35:01+00:00`. The local raw sample and probe metadata are Git ignored.

## Time and identity

- An individual vehicle's `VehiclePosition.timestamp` is the measurement time for that position. The `FeedHeader.timestamp` is the source's feed-creation time. Request start and response receipt times describe our collection, not when a vehicle was measured. Preserve these meanings separately; do not substitute ingestion time for an absent vehicle measurement time without an explicit later rule.
- SHA-256 of the exact complete response bytes identifies payload content. Every HTTP poll has its own request identity and metadata. Two successful polls returning identical bytes share one payload content identity but retain two distinct request records and receipt times. Neither poll overwrites the earlier record.

## Failure and restart examples

| Case | Retained evidence | Payload snapshot |
| --- | --- | --- |
| Two complete identical responses | One exact-byte payload under one hash; two request records with distinct request/receipt times | One content identity referenced by both requests |
| Request times out before any bytes arrive | Request ID, URL, UTC start/failure times and timeout error | None; do not infer absent vehicle service |
| Process restarts with a prior `started` request | Preserve its request ID and original start time; mark `interrupted` with a detection time, leaving the response outcome unknown. The next poll gets a new request ID. | None unless the prior request already completed and was linked to a retained complete payload |
| A complete response cannot be parsed as GTFS Realtime Protobuf | Retain the exact complete bytes under their SHA-256 hash and link every request to that byte artifact, HTTP status, and parse error. Repeated identical malformed responses share the artifact but keep separate request records. | No valid Vehicle Positions snapshot; do not use the bytes for vehicle analysis |
| HTTP error with a complete response body | Retain the exact bytes under their SHA-256 hash and link each request to the HTTP status and error. The request remains failed even if the body parses as Protobuf. | No valid Vehicle Positions snapshot |

If a staging file contains only partial bytes at restart, record that the file existed and its observed byte count, mark the attempt interrupted, then discard the partial staging file. Do not create a payload hash, content identity, or selectable snapshot from partial bytes. The staging file is incomplete transfer state, not an immutable source snapshot.

## Still open

The finite collector stores separate `requests/<id>.json` records, transient `.part` staging, and immutable complete `payloads/<sha256>/response.pb` artifacts. Startup reconciliation implements the bounded interrupted-request rule above. These mechanics are tested and independently reviewed; they do not establish general crash or power-loss recovery.

Production polling cadence, response-size limits, continuous operation, retry/backoff, broader recovery, single-writer enforcement, and stored-payload tamper detection remain open. Clean dependency installation is unverified; current passing runs use a local vendor directory. A successful HTTP response is not by itself evidence that the feed or individual vehicle observations are fresh. This contract covers the first Vehicle Positions slice only; Trip Updates and Alerts follow later.
