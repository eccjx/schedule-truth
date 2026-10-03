# Current Project State

Last updated: 2026-10-01. Base: `3ba829d` on `main`; working tree was clean before this state reconciliation. `91e0b5b` records the accepted Phase 1 work; `3ba829d` adds the Vehicle Positions slice, its accepted contract, dependencies, and tests.

## Current Phase

**Phase 1 accepted by the author on 2026-09-30** against the four completion criteria in `ROADMAP.md`: identical downloads share one content identity, changed bytes create separate versions, historical ZIPs are preserved, and persisted metadata is queryable. Phase 0 foundations are substantially implemented but formal acceptance remains separate. **Phase 2 is in progress:** the bounded Vehicle Positions slice is implemented, independently tested/reviewed, and committed. Phase 2 as a whole is not accepted.

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
- The accepted Vehicle Positions contract distinguishes vehicle measurement time, feed creation time, and local request/receipt times. Exact complete response bytes have SHA-256 identity; every poll has a separate request record, including identical-byte polls. Complete malformed/HTTP-error bodies remain failed evidence; incomplete transfers have observed byte counts and no payload identity.
- `collect_vehicle_positions` supports finite configurable polling and startup reconciliation: prior started requests become interrupted/unknown, original identity/start time is preserved, partial staging is recorded/discarded, and completed records remain unchanged. Synthetic duplicate, failure, and bounded restart cases pass independent checks.
- Three real October 1 Vehicle Positions polls returned distinct hashes with 75,655, 75,343, and 75,154 bytes. Persisted bytes, source timestamps, aware-UTC collection times, and earlier-file preservation were checked. Independent inspection decoded the three saved payloads and cross-checked their metadata. Local live evidence remains Git ignored.

## In Progress

- The Vehicle Positions slice is finite, not an established continuous service. Production cadence, retry/backoff, shutdown behavior, and response-size bounds remain undecided; Trip Updates and Service Alerts are not implemented.
- Original-report/revision persistence remains unfinished under the accepted snapshot design.
- Static collection remains one request per call; periodic invocation, retries, and operational recovery are not demonstrated.

## Blocked and Known Limits

- No remaining failing Phase 1 test blocks the accepted scope.
- Existing extracted `feed/` files are trusted. Changed cached CSVs can affect a trace despite a valid retained ZIP; recreate disposable extraction from the verified ZIP when in doubt. Automatic comparison/rebuild remains unfinished.
- Static writes are not transactional. Interruptions/storage failures can leave started attempts, staged bytes, temporary JSON, or unlinked receipts. Static recovery is not established.
- Realtime startup recovery covers readable started/interrupted request records only. Single-writer ownership is assumed, not enforced. Malformed metadata, orphan artifacts, storage errors, process-kill/power-loss recovery, and concurrency remain outside the verified contract. Existing payloads are trusted rather than rehashed; memory grows with the finite result list and complete bodies are read into memory.
- `valid_snapshot` means successful complete HTTP transport and initialized protobuf decoding. It does not establish freshness, healthy service, coordinate validity, or missing-service semantics.

## Needs Verification

- Phase 1 and Vehicle Positions source/tests are committed. Ignored data, private evidence, and the local dependency vendor directory do not travel with source commits.
- Duplicate MBTA rows, multiple feed-info rows, oversized agency CSV, malformed metadata recovery, and performance remain outside established contracts.
- Conda Python loads timezone data; `C:\Python314\python.exe` lacks it. `requirements.txt` now declares the realtime bindings and protobuf decoder; passing runs use ignored `.local/vendor` through PYTHONPATH. A clean dependency installation and installed source package are not verified; timezone portability remains unresolved. Phase 0's command-line example hardcodes a date. `README.md`, `DATA_MODEL.md`, and `LEARNING.md` remain empty.
- Continuous operation and restart preservation must be demonstrated for Phase 2; static one-request success does not establish these guarantees.

## Test Status

- **PASS, independently rerun 2026-10-01:** with `PYTHONPATH` set to this checkout's `.local/vendor`, `C:\Users\EricChen\miniconda3\python.exe -B -m unittest discover -s tests -q` — 128 tests, OK, including 16 Vehicle Positions tests and retained-ZIP mismatch.
- **PASS, recorded live evidence and independent persisted inspection:** two real HTTPS downloads, separate receipts/shared content, retained hash, 32 cached members, and October 1 persisted trace.
- **PASS, reported live realtime evidence and independent persisted inspection:** three finite Vehicle Positions polls; distinct payloads and timestamp metadata verified. Duplicate-byte handling and failure/restart behavior were exercised with fixtures, not live failures.
- Committed Vehicle Positions collector and requirements SHA-256 values match the independent review. Earlier review handoffs describe these files as untracked; commit `3ba829d` supersedes that source-status wording.
- **NOT RUN in this reconciliation:** new network fetch, continuous-service demonstration, clean dependency installation, process-kill/storage-failure recovery, concurrency, lint, and default-Python portability. Earlier live observations are distinct from this session's suite rerun.

## Important Findings and Learning

Content identity differs from request/receipt identity: identical bytes still carry separate availability evidence. Retained-ZIP validation does not authenticate cached CSVs. Realtime work must separate event/feed timestamps from request/receipt timestamps; missing observations must not imply missing transit service.

## Next Recommended Work

### Human-led engineering

1. Define continuous-operation behavior with the proven Vehicle Positions slice: cadence, what happens after a failed poll, bounded resource use, shutdown, and single-writer ownership. Do not infer a broader recovery promise from startup reconciliation.
2. Inspect Trip Updates and define its first collection slice, preserving exact bytes and distinguishing prediction/event timestamps from feed/collection times. Expand to Service Alerts afterward; broader interpretation remains later work.

### Verification and support work

- Add runner/transport/storage plumbing only against the agreed contract. Preserve existing raw-byte, request-identity, and timestamp semantics.
- Verify sustained polling, bounded result retention, failures followed by recovery, and stop/restart preservation; separately verify a clean dependency installation without `.local/vendor`.
- Assess new feed integration and continuous-operation evidence independently before Phase 2 acceptance. Roadmap intervals remain adjustable suggestions.

## Roadmap Impact

Phase 1 collection/versioning is author accepted within its explicit local scope. Phase 2 adds continuous realtime evidence capture and restart preservation. Raw-layer/manifest completion, normalization, feed health, reconciliation, reconstruction, replay, analytics, and operations remain ahead. Static scheduling, cache integrity, and report persistence remain visible follow-ups.
