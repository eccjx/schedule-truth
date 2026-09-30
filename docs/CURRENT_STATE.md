# Current Project State

Last updated: 2026-09-30. Base: `b11ddb8` on `main`, plus uncommitted collector, archive/trace fixes, tests, and documentation. Acceptance applies to this working tree, not HEAD alone.

## Current Phase

**Phase 1 accepted by the author on 2026-09-30** against the four completion criteria in `ROADMAP.md`: identical downloads share one content identity, changed bytes create separate versions, historical ZIPs are preserved, and persisted metadata is queryable. Phase 0 foundations are substantially implemented but formal acceptance remains separate. Phase 2 realtime collection is next; no realtime implementation is present.

Acceptance does not establish continuous static polling, automatic retry, crash recovery, extraction-cache verification, or persistent original-report/revision records. These remain follow-ups rather than additional Phase 1 acceptance gates.

## Completed and Tested Scope

- Schedule helpers, service-date resolution, normalization/loaders, selection, and parameterized tracing are implemented across earlier commits and the current working tree.
- Local archives retain ZIP bytes under SHA-256 identity, content metadata, and separate aware-UTC receipts. Invalid/missing coverage yields null dates and diagnostics; such snapshots are ineligible for historical selection.
- MBTA agency-row selection and recorded `America/New_York` fallback are implemented. Historical selection uses the latest eligible receipt by MBTA-local midnight. Caller or selected-archive timezone mismatches explicitly fail.
- The one-request HTTP collector persists attempts and outcomes. Invalid ZIP bytes and bodies accompanying request failures remain evidence without successful receipts or selectable schedule metadata. Unsupported/encrypted ZIP validation and oversized coverage CSV cases have regressions.
- Retained ZIP SHA-256 is recomputed before extraction. Replaced bytes are rejected; the formerly failing integrity regression passes. Existing extracted files remain trusted.
- Two real MBTA HTTPS collections on September 30 returned identical 24,684,859-byte ZIPs: one content identity, two attempts and receipts. SHA-256: `da552d2330c9b85c2ad7ddb5d71012bb9539b2ba5b822d7000d7a3606ec79296`. Receipt times: `2026-09-30T22:13:16.048740+00:00` and `2026-09-30T22:13:41.783124+00:00`. Coverage: September 22–December 12, 2026.
- Persisted selection for October 1 chose the second receipt. Trip `78942566` traced 45 visits, stop `1747` at `19:10:00` through stop `797` at `20:03:00`. Independent inspection verified retained bytes and all 32 extracted ZIP members. Archives are Git ignored and do not travel with source commits.
- The earlier September 29 archive/September 30 trace remain local evidence; their supplied download time was only known to the minute. New collector receipts record observed UTC timestamps at microsecond resolution.

## In Progress

- Phase 2 contract and first realtime collector slice are not implemented. The roadmap calls for Vehicle Positions, Trip Updates, and Service Alerts, preserving exact protobuf payloads and request evidence locally.
- Original-report/revision persistence remains unfinished under the accepted snapshot design.
- Static collection remains one request per call; periodic invocation, retries, and operational recovery are not demonstrated.

## Blocked and Known Limits

- No remaining failing Phase 1 test blocks the accepted scope.
- Existing extracted `feed/` files are trusted. Changed cached CSVs can affect a trace despite a valid retained ZIP; recreate disposable extraction from the verified ZIP when in doubt. Automatic comparison/rebuild remains unfinished.
- Writes are not transactional. Interruptions/storage failures can leave started attempts, staged bytes, temporary JSON, or unlinked receipts. Recovery and concurrency guarantees are not established.

## Needs Verification

- Source changes include untracked collector/tests; a committed revision is needed to reproduce acceptance from another checkout. Ignored data and private evidence remain local.
- Duplicate MBTA rows, multiple feed-info rows, oversized agency CSV, malformed metadata recovery, and performance remain outside established contracts.
- Conda Python loads timezone data; `C:\Python314\python.exe` lacks it. Package/dependency declarations are absent. Phase 0's command-line example hardcodes a date. `README.md`, `DATA_MODEL.md`, and `LEARNING.md` remain empty.
- Continuous operation and restart preservation must be demonstrated for Phase 2; static one-request success does not establish these guarantees.

## Test Status

- **PASS, independently rerun 2026-09-30:** `C:\Users\EricChen\miniconda3\python.exe -B -m unittest discover -s tests -q` — 112 tests, OK, including retained-ZIP mismatch.
- **PASS, recorded live evidence and independent persisted inspection:** two real HTTPS downloads, separate receipts/shared content, retained hash, 32 cached members, and October 1 persisted trace.
- Current archive, collector, and trace source SHA-256 values match the independent acceptance review.
- **NOT RUN in this reconciliation:** new network fetch, continuous polling, process-kill/storage-failure recovery, concurrency, lint, and default-Python portability. Earlier live observations are distinct from this session's suite rerun.

## Important Findings and Learning

Content identity differs from request/receipt identity: identical bytes still carry separate availability evidence. Retained-ZIP validation does not authenticate cached CSVs. Realtime work must separate event/feed timestamps from request/receipt timestamps; missing observations must not imply missing transit service.

## Next Recommended Work

1. Define the first realtime collection contract using Vehicle Positions: attempt/payload identity, timestamp meanings, failure evidence, and minimum restart-preservation boundary. These decisions remain proposed until accepted.
2. Build a single-feed polling slice with immutable raw protobuf storage; verify duplicates, failed requests, and stop/restart behavior.
3. Expand to Trip Updates and Service Alerts before Phase 2 acceptance. Roadmap polling intervals are adjustable suggestions, not an accepted operational contract.

## Roadmap Impact

Phase 1 collection/versioning is author accepted within its explicit local scope. Phase 2 adds continuous realtime evidence capture and restart preservation. Raw-layer/manifest completion, normalization, feed health, reconciliation, reconstruction, replay, analytics, and operations remain ahead. Static scheduling, cache integrity, and report persistence remain visible follow-ups.
