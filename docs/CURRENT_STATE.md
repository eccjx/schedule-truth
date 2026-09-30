# Current Project State

Last updated: 2026-09-29. Base revision: `2389875` on `main`, with uncommitted code, tests, and documentation.

## Current Phase

Phase 0 GTFS foundations are substantially implemented but not formally accepted. Phase 1 static schedule versioning now has local ZIP/receipt archiving, snapshot selection, persisted metadata loading, extraction, and a demonstrated real retained-ZIP trace. The HTTP collector, corrupt-ZIP/fetch-failure policy, report revisions, and independent review remain. Phase 1 is not accepted.

## Completed and Tested Scope

- Earlier commits `12e9221`, `18fbe60`, `3ddd08e`, `ac8c2ba`, and `10f93fe` provide schedule helpers, normalization/loaders, selection, and the parameterized trace.
- `2389875` provides SHA-256 local ZIP archiving, content JSON, separate UTC receipt JSON, and strict coverage parsing. Repeated identical bytes retain one content identity and separate receipts in tested cases.
- Current working code selects the MBTA `agency.txt` row even when another agency comes first. Missing/invalid MBTA timezone uses the recorded `America/New_York` fallback. The archive loader restores typed content and receipt metadata; extraction uses a hash-named `feed/` directory; `trace_from_archive` selects from persisted receipts.
- A real MBTA ZIP received on 2026-09-29 at approximately 11:35 PDT (18:35 UTC, supplied only to minute precision) was archived under SHA-256 `e3fdffe291bbe715d09356c1f2ceb58c8fc0781478e4041ba46160d964723133`. Receipt `2851b820e5764bf29ce9f1a8931a2ecc` and content metadata are present. The retained ZIP hash was independently recomputed and matched. A 2026-09-30 trace of trip `78942566` used that archive and returned 45 visits, stop `1747` at `19:10:00` through stop `797` at `20:03:00`.
- The accepted missing/invalid coverage-retention and MBTA-row/fallback decisions are recorded in the snapshot decision and plan. `data/` is ignored by Git; the real ZIP/archive are local evidence, not tracked project files.

## In Progress

- A one-fetch HTTP collector has not been built. No persisted original-report/revision identity or current-versus-prior revision retrieval exists.
- Source timezone is stored with content, while `trace_from_archive` still takes an independent `agency_timezone` argument. The intended handling of a mismatch needs author review.
- The real archive proves one eligible service-date/trip path. It does not prove continuous collection, all feed layouts, or automatic archive integrity checks.

## Blocked and Known Failure

- **Phase 1 acceptance is blocked by one known red integrity test.** If `<hash>/original.zip` is replaced with different valid ZIP bytes, extraction can trace the replacement while reporting the old hash and receipt. The author explicitly deferred automatic integrity detection on 2026-09-29; the failing regression remains in place and is documented in `FAILURE_MODES.md`.
- Corrupt-ZIP and partial-persistence outcomes are not yet decided. The current archiver writes bytes before ZIP/metadata validation, so a failure can leave bytes without a receipt.

## Needs Verification

- The latest full suite has one failure, so the current working revision is not green or independently reviewed. Multiple MBTA rows, multiple `feed_info.txt` rows, malformed persisted metadata recovery, interrupted writes, concurrency, and performance remain outside established contracts.
- The receipt timestamp for the real download is only known to the minute. Saved `:00` seconds and zero microseconds represent the supplied minute; they were not observed with finer precision.
- The Phase 0 command-line entry point still hardcodes one example although its Python function accepts a date. Phase 0 acceptance is the author's decision.
- `C:\Python314\python.exe` lacks IANA timezone data; Conda Python works. No project dependency declaration yet ensures reproducibility in both environments.

## Test Status

- **FAIL:** `C:\Users\EricChen\miniconda3\python.exe -B -m unittest discover -s tests -q` on 2026-09-29 ran 90 tests with one failure: `test_mismatched_retained_zip_cannot_be_traced_under_old_hash`. The test deliberately replaces retained ZIP bytes and exposes false hash provenance.
- **PASS (handoff):** the archive-specific suite ran 18 tests after the author's missing-MBTA error-message fix. Earlier full-suite results with two failures predate that fix.
- **PASS (reported real check):** persisted ZIP/receipt selection, extraction, and the 45-visit September 30 MBTA trace; retained ZIP SHA-256 recomputation independently matches metadata.
- **NOT RUN:** a new independent review after the final working-tree changes; HTTP collector tests; corrupt-ZIP persistence tests; lint.

## Important Findings and Learning

- Independent synthetic tests confirm persisted receipts, cutoff selection, repeated-content receipt identity, unresolved outcomes, and deterministic archive tracing within tested scope.
- The real ZIP has Cape Cod Regional Transit Authority first and MBTA second; selecting the first agency row would have been an unsupported assumption. The author corrected MBTA-row selection and verified the fallback reason for a missing MBTA row.
- The trace prints a selected path and receipt, but derived report records and revision IDs are not persisted. An altered retained ZIP can undermine the printed provenance.
- `README.md`, `DATA_MODEL.md`, and `LEARNING.md` remain empty; Python package/dependency setup is absent.

## Next Recommended Work

### Human-led engineering

1. MUST — With Mentor, decide and document what a corrupt ZIP and failed static-feed fetch retain: attempted request, received bytes, content record, receipt, and error. Implement the bounded archive/collector behavior after the outcomes are explicit. Stop when examples cannot leave an ambiguous unrecorded partial attempt.
2. SHOULD — Define the source of agency timezone for historical trace selection from persisted metadata and the outcome when a caller-supplied value disagrees. Stop when one trace cannot silently use a timezone inconsistent with its archived schedule evidence.
3. STRETCH — Sketch stable original-report and later-revision identities linked to selected hash and receipt. Stop at a small example showing that a later schedule cannot silently overwrite the original.

### Verification and support work

- Builder (proposed, after failure outcomes): implement bounded HTTP/retry/CLI and dependency plumbing without choosing collector failure semantics.
- Tester (proposed, after the author's handling): test corrupt ZIP/fetch failure artifacts and timezone mismatch; keep the deferred retained-ZIP identity regression visible.
- Reviewer (proposed): independently assess the current archive/trace path, accepted decisions, failure handling, and remaining Phase 1 criteria; report actionable findings.
- Planner: this state reconciles the September 29 handoffs, real archive evidence, and the current 90-test run. Proposed support work was not launched here.

## Roadmap Impact

Phase 1 has advanced from local archiving to a real versioned static trace, but continuous collection and safe failure behavior remain. The deferred integrity defect blocks Phase 1 acceptance. Realtime collection and later reconstruction, analytics, replay, and operational work remain ahead under the accepted roadmap.
