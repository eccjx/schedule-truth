# Current Project State

Last updated: 2026-09-25. Revision checked: `10f93fe` on `main`; the working tree was clean before this reconciliation.

## Current Phase

The accepted `ROADMAP.md` places the project at the end of Phase 0 (GTFS foundations) and in Phase 1 (static schedule collection and versioning). Date-aware schedule helpers, CSV loading, and a parameterized trip trace are implemented. An in-memory historical snapshot selector and archive-path trace wrapper are implemented and tested; collection, immutable ZIP storage, persisted receipts, and report revisions remain.

## Completed

- `12e9221`: time and service-date helpers.
- `18fbe60`: trip helpers and schedule composition.
- `3ddd08e`: normalizers and associated tests.
- `ac8c2ba`: CSV loaders, initial trace, accepted snapshot-selection decision, and initial selector.
- `10f93fe`: selector validation for coverage and UTC receipts, parameterized trace, archive-path wrapper, and 12 new selector/wrapper test methods. The supplied roadmap is committed.
- The accepted snapshot decision specifies agency-local midnight, inclusive `feed_info.txt` coverage, SHA-256 ZIP identity, separate UTC receipt records, and distinct later revisions. Acceptance of the design does not imply Phase 1 completion.

## In Progress

- `select_schedule_snapshot` chooses the latest eligible in-memory receipt and returns unresolved when none qualifies. `trace_from_archive` maps the chosen hash to an extraction directory and prints the hash path and receipt before tracing.
- Phase 1 still needs a collector, validation and immutable retention of original ZIPs, separate persisted receipts for repeated downloads, extract-by-hash behavior, queryable metadata, and a trace backed by an actual archived ZIP.

## Blocked

- None confirmed for development in Conda Python.

## Needs Verification

- Phase 0's service-date input is now available through the `main(feed_path, service_date, trip_id)` function. Its command-line entry point still hardcodes one example; whether the Phase 0 completion criterion requires a user-facing CLI is an author milestone decision. No phase acceptance is recorded.
- Selector and wrapper tests are green, but the wrapper tests mock CSV loading; they do not prove an end-to-end archived-ZIP trace. There is no independent review of `10f93fe`.
- `agency_timezone` is passed to the selector; extracting it from the MBTA `agency.txt` row is not implemented. Receipt records, original-report/revision identities, and archive immutability are design only.
- The accepted first-version rule leaves selection among distinct ZIP contents with identical receipt timestamps undefined. The current sort would use input order if this occurs; do not treat that as an accepted tie rule.
- `C:\Python314\python.exe` lacks IANA timezone data and cannot load `America/New_York`; Conda Python works. No dependency declaration currently makes both environments reproducible.
- Earlier helper/normalizer malformed-row and duplicate/conflict policies remain limited or unspecified. The prior real-feed trace lacks recorded ZIP provenance.

## Test Status

- PASS: `C:\Users\EricChen\miniconda3\python.exe -B -m unittest discover -s tests -q` ran 67 tests on 2026-09-25, outside the Windows temporary-directory sandbox restriction.
- The prior Tester handoff recorded six missing-coverage errors against pre-commit working code. The committed `10f93fe` selector uses `.get()` for coverage and the current 67-test run passes; that handoff finding is resolved in the tested scope.
- PASS (prior check): The unversioned MBTA trace returned 45 visits for trip `78942566` on 2026-09-22, from stop `1747` at `19:10:00` to stop `797` at `20:03:00`.
- NOT RUN: End-to-end trace from a retained ZIP, duplicate-download collector behavior, report revision retrieval, independent review, and lint.

## Important Findings and Risks

- The 12 new test methods cover seasonal midnight cutoffs at microsecond precision, coverage bounds and invalidity, UTC receipt validation, unresolved selection, and wrapper routing/provenance. They do not exercise ZIP collection or persisted metadata.
- The trace wrapper currently prints selected path and receipt; it does not store a derived report with stable identity. An arbitrary metadata list and extraction directory are supplied by the caller.
- The repository has no declared Python package/dependency setup. `README.md`, `DATA_MODEL.md`, `FAILURE_MODES.md`, and `LEARNING.md` are empty.

## Learning Progress

- The accepted decision and authored selector express the author's reasoning about historical schedule evidence, local-midnight cutoffs, coverage, and UTC receipts.
- Archive ingestion, repeated-content receipts, report revisions, and later realtime reconciliation remain the next core learning areas.

## Next Recommended Work

### Human-led engineering

1. MUST — Define and implement the smallest Phase 1 archive/receipt contract around one downloaded ZIP: immutable original bytes, SHA-256 identity, precise UTC receipt, `feed_info.txt` coverage, and MBTA agency timezone. Stop when two identical downloads share content identity while retaining two receipt records, and a new ZIP gets a new content directory.
2. SHOULD — Use that contract to drive `trace_from_archive` with real persisted metadata and files. Stop when one service date/trip trace can be reproduced from the retained ZIP and its selected receipt, without inventing provenance for the earlier 45-visit example.
3. STRETCH — Review Phase 0's parameterized API against the roadmap completion criteria and record whether a CLI is needed before author acceptance.

### Verification and support work

- Builder (proposed, after the author's archive contract): implement bounded HTTP/retry, ZIP-validation, extraction, CLI, and dependency plumbing without choosing schedule-version semantics; report paths and metadata produced.
- Tester (proposed, after archive implementation): test repeated identical downloads, new content, failed/corrupt ZIP, immutable storage, receipt selection, and a real archived fixture trace; report reproductions, without changing core semantics.
- Reviewer (proposed): independently assess `10f93fe` and later archive integration against the accepted decision and tests; report concrete gaps before milestone acceptance.
- Planner: this state reconciles `10f93fe`, the September 25 handoff, and the 67-test rerun.

## Roadmap Impact

Phase 0 behavior is substantially implemented and tested, with acceptance still for the author to record. Phase 1 has moved from design and initial selector to a tested selector plus trace wrapper. The roadmap's Week 1 versioned-ingestion deliverable is still incomplete because the collector, immutable archive, and queryable receipts are absent. Phases 2–16 and 20 remain ahead; Phases 17–19 are conditional on demonstrated need.
