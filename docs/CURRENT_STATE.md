# Current Project State

Last updated: 2026-10-02. Base: `f19750a` on `main`; working tree was clean before this reconciliation. This revision commits the Vehicle Positions continuous runner/deadline, tests, and approved Trip Updates collection semantics. Earlier handoffs describing these files as uncommitted are superseded by this revision.

## Current Phase

**Phase 1 accepted by the author on 2026-09-30** against the four completion criteria in `ROADMAP.md`: identical downloads share one content identity, changed bytes create separate versions, historical ZIPs are preserved, and persisted metadata is queryable. Phase 0 formal acceptance remains separate. **Phase 2 is in progress:** the Vehicle Positions collection and continuous-runner slices are implemented, independently tested/reviewed, and committed; the author accepted the bounded runner on October 2. Trip Updates collection semantics are approved but not implemented. Phase 2 as a whole is not accepted.

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
- The Windows continuous runner polls sequentially, defaults to a configurable 15-second completion-to-next-start delay after success or failure, performs startup reconciliation, and does not accumulate a result history. A machine-local mutex excludes another cooperating writer before recovery/writes; the finite collector uses the same guard.
- The runner defaults to a configurable 10 MiB response limit and 120-second monotonic network-reception deadline. Expired/oversized transfers retain failure evidence and observed byte counts, discard partial staging, and create no payload identity. Graceful stop preserves the original deadline and starts no subsequent poll. An isolated transport worker is terminated on deadline or parent exit. Real Windows loopback/process tests cover slow-drip/blocked reception, stopping, ownership, and restart preservation; accelerated allocation checks cover result-history accumulation.
- Approved Trip Updates semantics distinguish stop-event values, trip-update time, feed creation, and local collection time. An ad hoc 942,790-byte/1,595-entity sample informed the contract but lacks collection-grade receipt evidence. Past stop-time values are not automatically confirmed actual events; missing updates imply neither on-time nor absent service.

## In Progress

- The Vehicle Positions continuous runner is implemented and accepted within its bounded Windows scope. A live continuous-runner soak is not demonstrated. Trip Updates transport/storage/runner integration remains unimplemented; its cadence, size bounds, and integration choices remain open. Service Alerts contract and collection are not implemented.
- Original-report/revision persistence remains unfinished under the accepted snapshot design.
- Static collection remains one request per call; periodic invocation, retries, and operational recovery are not demonstrated.

## Blocked and Known Limits

- No remaining failing Phase 1 test blocks the accepted scope.
- Existing extracted `feed/` files are trusted. Changed cached CSVs can affect a trace despite a valid retained ZIP; recreate disposable extraction from the verified ZIP when in doubt. Automatic comparison/rebuild remains unfinished.
- Static writes are not transactional. Interruptions/storage failures can leave started attempts, staged bytes, temporary JSON, or unlinked receipts. Static recovery is not established.
- Realtime startup recovery covers readable started/interrupted records only. Windows machine-local cooperating writers are excluded by a root mutex; multi-host/alias/noncooperating mutation is not covered. Malformed metadata, orphan artifacts, storage errors, and power-loss recovery remain outside the verified contract. Existing payloads are trusted rather than rehashed. The finite API retains a result list; the continuous runner does not. Complete bounded bodies and decoded summaries are loaded into memory; worst-case/native RSS is not measured.
- The runner deadline bounds network reception, not end-to-end finalization or process exit. Process creation/cleanup, hashing/decoding and filesystem operations may outlive it. Finalized evidence can fail under storage faults. Actual parent-crash worker lifetime was tested, but general process-kill/storage recovery was not established.
- `valid_snapshot` means successful complete HTTP transport and initialized protobuf decoding. It does not establish freshness, healthy service, coordinate validity, or missing-service semantics.

## Needs Verification

- Phase 1 and Vehicle Positions source/tests are committed. Ignored data, private evidence, and the local dependency vendor directory do not travel with source commits.
- Duplicate MBTA rows, multiple feed-info rows, oversized agency CSV, malformed metadata recovery, and performance remain outside established contracts.
- Conda Python loads timezone data; `C:\Python314\python.exe` lacks it. `requirements.txt` now declares the realtime bindings and protobuf decoder; passing runs use ignored `.local/vendor` through PYTHONPATH. A clean dependency installation and installed source package are not verified; timezone portability remains unresolved. Phase 0's command-line example hardcodes a date. `README.md`, `DATA_MODEL.md`, and `LEARNING.md` remain empty.
- Phase 2 still needs Trip Updates and Alerts plus integrated continuous-collection evidence. Vehicle Positions continuous mechanics and bounded restart preservation are tested; live long-duration operation and clean deployment remain unverified.

## Test Status

- **PASS, independently rerun 2026-10-02 at `f19750a`:** with `PYTHONPATH` set to this checkout's `.local/vendor`, `C:\Users\EricChen\miniconda3\python.exe -B -m unittest discover -s tests -q` — 151 tests, OK. Covers inherited static/realtime cases and new runner/deadline cases.
- **PASS, recorded live evidence and independent persisted inspection:** two real HTTPS downloads, separate receipts/shared content, retained hash, 32 cached members, and October 1 persisted trace.
- **PASS, reported live realtime evidence and independent persisted inspection:** three finite Vehicle Positions polls; distinct payloads and timestamp metadata verified. Duplicate-byte handling and failure/restart behavior were exercised with fixtures, not live failures.
- Committed runner, collector, worker, job, and ownership source SHA-256 values match the October 2 independent review. Review found no concrete defect in the approved bounded slice; no Phase 2 acceptance was declared.
- **NOT RUN in this reconciliation:** new live fetch/runner soak, clean dependency installation, generalized power-loss/storage-fault recovery, multi-host concurrency, lint, and default-Python portability. Local loopback/process tests and prior finite live observations are distinct from a live continuous-service demonstration.

## Important Findings and Learning

Content identity differs from request/receipt identity: identical bytes still carry separate availability evidence. Retained-ZIP validation does not authenticate cached CSVs. Realtime work must separate event/feed timestamps from request/receipt timestamps; missing observations must not imply missing transit service.

## Next Recommended Work

### Human-led engineering

1. Complete the Trip Updates integration choices against its approved collection semantics: cadence, size/deadline behavior, feed labeling, archive-root ownership, and which existing runner mechanics to reuse. Keep stop-event classification outside collection.
2. Pair on the first Trip Updates collector/runner slice, preserving exact payload bytes, distinct poll identities and approved failure/restart meanings.
3. Inspect Service Alerts and define its raw-collection contract, separating alert active periods from feed/receipt time.

### Verification and support work

- Adapt transport/storage/runner plumbing only after the Trip Updates integration choices are approved; preserve feed labels, exact bytes, request identities and timestamp semantics.
- Verify Trip Updates duplicates, source-time preservation, malformed/HTTP/incomplete failures, deadline/size limits and restart history; separately verify clean installation and a bounded live Vehicle Positions runner stop/restart demonstration.
- Assess new-feed integration and continuous-operation evidence independently before Phase 2 acceptance. A short live demonstration is incremental evidence, not proof of indefinite reliability.

## Roadmap Impact

Phase 1 collection/versioning is author accepted within its explicit local scope. Phase 2 adds continuous realtime evidence capture and restart preservation. Raw-layer/manifest completion, normalization, feed health, reconciliation, reconstruction, replay, analytics, and operations remain ahead. Static scheduling, cache integrity, and report persistence remain visible follow-ups.
