# Current Project State

Last updated: 2026-11-02, end of session. Base: `7edcffe` on `main`, with uncommitted completed Trip Updates inspector, eight independent tests, first Alerts persistence module, and state documentation. Inspector acceptance applies to the current working tree; Alerts persistence is not accepted.

## Current Phase

**Phase 1 accepted by the author on 2026-09-30** against its four roadmap completion criteria. Phase 0 formal acceptance remains separate. **Phase 2 is in progress:** Vehicle Positions and Trip Updates collector/runner slices are committed and accepted within their bounded scopes. The read-only Trip Updates inspector was tested, reviewed and author accepted November 2. Alerts complete-response persistence is implemented but awaits automated verification/review and acceptance; Alerts HTTP/runner remains absent. Phase 2 as a whole is not accepted.

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
- Trip Updates polls use a dedicated feed-labeled archive, configurable 30-second completion-to-start cadence, 10 MiB size cap and 120-second reception deadline, reusing reviewed Windows transport/ownership/recovery mechanics. Every poll has its own request record; exact complete bytes have SHA-256 content identity. Terminal no-payload requests cannot later be completed under the same ID.
- Exact completed-request replay verifies retained bytes and preserves historical request/payload bytes, mtimes and finish evidence. Changed bytes/status/request-start/receipt evidence is rejected before writes. Missing or corrupt terminal payloads are explicit errors. Payload creation/verification precedes finalized request linkage; this is not a multi-file transaction.
- One real October 5 Trip Updates poll retained 713,241 bytes under SHA-256 `a7193b2de3125bbe5edb810aff55429b09e3555c009afbf265c7049cf128780f`, received at `2026-10-05T23:55:04.144893+00:00`. Independent audit decoded 1,437 Trip Updates and 23,543 stop entries, verified source/local times and historical immutability.
- New Trip Updates request JSON contains compact scalar audit metadata, without per-trip/per-stop arrays. Exact protobuf retains those source fields for later reads. Temporary persistence of the retained live bytes measured an adjusted 831-byte compact record versus the historical 5,444,599-byte expanded JSON. This is one sample measurement, not a fixed record-size guarantee or new compact-format live collection. Historical expanded records remain unchanged.
- README now documents current capabilities, setup guidance, examples, and limits. Its setup instructions do not establish that a clean installation has been verified.

## In Progress

- Vehicle Positions and Trip Updates runners are accepted within bounded Windows scopes. Sustained live-runner evidence and cross-feed operations remain unfinished. Alerts has a first complete-response persistence implementation; HTTP/runner behavior remains undecided/unimplemented.
- `inspect_trip_updates.inspect_trip_stop` is complete and author accepted in its bounded read-only scope. It verifies canonical payload bytes, initialized decoding and snapshot evidence, rejects missing/ambiguous trip-stop matches, preserves absent optional times as `None`, and returns source times separately from receipt time. Eight independent tests and review establish archive bytes/mtimes remain unchanged. Seven fixture tests are portable; the supplemental retained-live test skips when ignored data is absent.
- `collect_alerts.persist_alerts_response` implements exact-byte complete-response persistence with compact `service_alerts` metadata, replay/conflict and terminal-no-payload rules, payload verification before reuse, payload-before-final-request linkage, and complete malformed/HTTP-error evidence. It does not implement HTTP reception, partial-transfer handling or startup/runner integration. Automated verification and acceptance remain pending.
- Manual Alerts persistence check used an ignored 328,610-byte/147-entity probe: two requests shared one payload and exact replay preserved the record. The probe lacks collection-grade receipt evidence. Alert active periods are source display intervals, not receipt times or proof of actual disruption; periods remain in raw protobuf, not expanded request JSON.
- Original-report/revision persistence remains unfinished under the accepted snapshot design.
- Static collection remains one request per call; periodic invocation, retries, and operational recovery are not demonstrated.

## Blocked and Known Limits

- No remaining failing Phase 1 test blocks the accepted scope.
- Existing extracted `feed/` files are trusted. Changed cached CSVs can affect a trace despite a valid retained ZIP; recreate disposable extraction from the verified ZIP when in doubt. Automatic comparison/rebuild remains unfinished.
- Static writes are not transactional. Interruptions/storage failures can leave started attempts, staged bytes, temporary JSON, or unlinked receipts. Static recovery is not established.
- Realtime startup recovery covers readable started/interrupted records only. Windows machine-local cooperating writers are excluded by a root mutex; multi-host/alias/noncooperating mutation is not covered. Malformed metadata, orphan artifacts, storage errors and power-loss recovery remain outside the verified contract. Vehicle Positions trusts existing payloads; Trip Updates verifies them before reuse/replay. The finite Vehicle Positions API retains a result list; continuous runners do not. Bounded bodies are loaded/decoded in memory; worst-case/native RSS is not measured.
- The runner deadline bounds network reception, not end-to-end finalization or process exit. Process creation/cleanup, hashing/decoding and filesystem operations may outlive it. Finalized evidence can fail under storage faults. Actual parent-crash worker lifetime was tested, but general process-kill/storage recovery was not established.
- `valid_snapshot` means successful complete HTTP transport and initialized protobuf decoding. It does not establish freshness, healthy service, coordinate validity, or missing-service semantics.

## Needs Verification

- Existing collector/runner slices are committed. Completed inspector source/tests and first Alerts module remain uncommitted. Ignored data, private evidence and vendor dependencies do not travel with source commits.
- Duplicate MBTA rows, multiple feed-info rows, oversized agency CSV, malformed metadata recovery, and performance remain outside established contracts.
- Conda Python loads timezone data; the earlier default-Python probe lacked it. `requirements.txt` declares realtime bindings/protobuf; passing runs use ignored `.local/vendor` through PYTHONPATH. Clean dependency installation and an installed source package remain unverified; README explains the current setup. Phase 0's command-line example hardcodes a date; `DATA_MODEL.md` and `LEARNING.md` remain empty.
- Phase 2 still needs Alerts and integrated continuous-collection evidence. Both implemented runners have bounded restart/failure tests; live long-duration operation and clean deployment remain unverified. No current compact-format live Trip Updates poll was observed in the recorded verification.

## Test Status

- **PASS, independently rerun end-of-session 2026-11-02:** with `PYTHONPATH` set to `.local/vendor`, `C:\Users\EricChen\miniconda3\python.exe -B -m unittest discover -s tests -p test_inspect_trip_updates_independent.py -q` — eight tests, OK. Source/test hashes match independent review.
- **PASS, reported full suite after inspector completion:** same Python/vendor environment, `-B -m unittest discover -s tests -q` — 188 tests, OK. This result predates the new Alerts module; no automated Alerts tests or post-Alerts full run are established. A green inherited suite would not validate Alerts persistence.
- **PASS, recorded live evidence and independent persisted inspection:** two real HTTPS downloads, separate receipts/shared content, retained hash, 32 cached members, and October 1 persisted trace.
- **PASS, reported live realtime evidence and independent persisted inspection:** three finite Vehicle Positions polls; distinct payloads and timestamp metadata verified. Duplicate-byte handling and failure/restart behavior were exercised with fixtures, not live failures.
- October 7 targeted review and retained-live-byte audits found no concrete defect in the approved Trip Updates slice. Since `ebbd0fe`, committed changes affect README, state/plan documentation and the partial reader, not collector/runner production code. Slice acceptance remains separate from Phase 2 milestone acceptance.
- **NOT RUN in this reconciliation:** new live fetch/runner soak, clean dependency installation, generalized power-loss/storage-fault recovery, multi-host concurrency, lint, and default-Python portability. Local loopback/process tests and prior finite live observations are distinct from a live continuous-service demonstration.

## Important Findings and Learning

Content identity differs from request/receipt identity: identical bytes still carry separate availability evidence. Retained-ZIP validation does not authenticate cached CSVs. Realtime work must separate event/feed timestamps from request/receipt timestamps; missing observations must not imply missing transit service.

## Next Recommended Work

### Human-led engineering

1. Define the bounded Alerts HTTP/runner contract: cadence, size/deadline limits, dedicated archive ownership, partial-response evidence and restart behavior. Preserve approved complete-response identity/time semantics. These operating choices remain proposals until author approved.
2. Author the first Alerts poll using existing transport as a reference, linking a complete response through persistence and recording incomplete failures without payload identity. Guidance should support an author attempt before any further delegated implementation.
3. After the poll works, integrate sequential execution, stop and bounded recovery against the approved contract. Resolve persistence findings before acceptance; do not infer a whole Phase 2 acceptance from a single successful poll.

### Verification and support work

- Inspector verification/review is complete within its bounded scope. Challenge Alerts persistence now: duplicate polls, exact replay, changed evidence, terminal-no-payload rejection, corrupt/missing payloads, failed complete bodies and archive immutability. Report concrete defects to the implementation owner; acceptance remains the author's decision.
- Verify clean installation without local vendor dependencies and bounded live runner stop/restart demonstrations in fresh archives, including current compact Trip Updates metadata. Report actual evidence and limits rather than claim long-duration reliability.
- Provide transport/CLI plumbing only when explicitly delegated. Independently assess the Alerts slice and multi-feed continuous-operation evidence before Phase 2 acceptance.

## Roadmap Impact

Phase 1 collection/versioning is author accepted within its explicit local scope. Phase 2 adds continuous realtime evidence capture and restart preservation. Raw-layer/manifest completion, normalization, feed health, reconciliation, reconstruction, replay, analytics, and operations remain ahead. Static scheduling, cache integrity, and report persistence remain visible follow-ups.
