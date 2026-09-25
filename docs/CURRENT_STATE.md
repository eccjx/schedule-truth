# Current Project State

Last updated: 2026-09-24. Revision checked: `ac8c2ba` on `main`; documentation changes are in the working tree.

## Current Phase

The author supplied and accepted `docs/ROADMAP.md` as the project scope and sequence. Phase 0 (GTFS foundations) is substantially implemented: static GTFS helpers, normalizers, CSV loaders, and a one-trip MBTA trace are committed. Phase 1 (static collection and versioning) has an accepted snapshot-selection rule and initial selector, but no collector or integrated archive. No phase has been recorded as formally accepted.

## Completed

- `12e9221`: GTFS time and service-date helpers.
- `18fbe60`: trip helpers and schedule composition.
- `3ddd08e`: GTFS normalizers and associated tests.
- `ac8c2ba`: four CSV loaders, trace script, loader/trace tests, snapshot-selection design, and initial selector.
- `docs/ROADMAP.md` now records the author's full Phase 0–20 roadmap, six-week milestone outline, ownership, and success criteria. Its dates are targets, not evidence of delivered capabilities.
- The accepted rule uses an agency-local midnight cutoff, inclusive `feed_info.txt` coverage, timezone-aware UTC receipt times, SHA-256 identity for original ZIP bytes, separate receipts, and separately identified later revisions. This is design acceptance, not feature completion.

## In Progress

- `select_schedule_snapshot` filters in-memory snapshot records by coverage and cutoff and chooses the latest receipt. It does not yet validate the accepted metadata contract or handle every unresolved condition.
- The trace still uses a hardcoded local feed path, date, and trip. It does not select an archived ZIP, record hash/receipt provenance, or produce a stable report/revision identity. The existing 45-visit trace remains an unversioned demonstration.

## Blocked

- None confirmed for core selector development: Conda Python runs the selector with `America/New_York`. Portability to `C:\Python314\python.exe` needs a documented IANA timezone-data dependency.

## Needs Verification

- Phase 0's completion criteria require a program accepting a service date. The current trace hardcodes date/trip/path; helper functions accept a date, but the end-to-end input criterion remains unverified.
- Phase 1's collector, immutable archive, queryable metadata, and versioned trace are not implemented. The roadmap's sample metadata is illustrative; the accepted snapshot-selection decision governs detailed semantics.
- Committed selector implementation passes five direct in-memory timezone examples under Conda Python, but dedicated tests and independent review are absent. A missing `feed_start_date` key raises `KeyError` instead of making coverage ineligible. Distinct contents with equal receipt times currently fall through to input order; the accepted first-version rule deliberately leaves that tie undefined, so report it for author judgment if observed.
- UTC awareness/precision, source `agency_timezone`, ZIP content identity, receipt records, archive immutability, and original/revision identity are specified but not enforced by the current selector or trace.
- Earlier helper/normalizer input policies remain limited or unspecified: malformed or duplicate rows, conflicting exceptions, and exact `dict` versus `defaultdict` behavior. Author acceptance of consequential generated behavior is not recorded.
- The author reported explaining the source rows behind the real-feed trace with Mentor, but no durable source-row explanation or independent review is recorded.

## Test Status

- PASS: `python -B -m unittest discover -s tests -q` ran 55 tests on 2026-09-24 outside the sandbox. The same sandboxed command encountered 40 Windows Temp permission errors; that run did not establish code failures.
- PASS (prior check): The trace against `data/raw/MBTA_GTFS` returned 45 visits for trip `78942566` on 2026-09-22, from stop `1747` at `19:10:00` to stop `797` at `20:03:00`.
- PASS: Direct selector checks with `C:\Users\EricChen\miniconda3\python.exe -B -c ...` on 2026-09-24 passed five in-memory examples: newer eligible receipt, after-midnight exclusion, exact-midnight inclusion, no eligible snapshot, and winter UTC offset. These are smoke checks, not committed tests.
- FAIL: A direct Conda-Python selector check with missing `feed_start_date` raised `KeyError`; the accepted decision makes unknown coverage ineligible.
- ENVIRONMENT LIMIT: The same selector cannot run under `C:\Python314\python.exe` because `ZoneInfo("America/New_York")` raises `ZoneInfoNotFoundError`; that interpreter has empty `TZPATH` and no `tzdata` package. The limitation is interpreter-specific.
- NOT RUN: Committed selector-specific tests, versioned trace integration, independent review, and lint. No selector tests are present in `tests/`.

## Important Findings and Risks

- Loader/trace tests cover UTF-8 CSV loading, normalization failures, empty visits, inactive trips, and source preservation. They do not establish snapshot identity or archive behavior.
- The selector's current unresolved result is a generic reason; the accepted plan calls for a recorded reason when no snapshot qualifies.
- The repository has no defined Python package/dependency setup. `README.md`, `DATA_MODEL.md`, `FAILURE_MODES.md`, and `LEARNING.md` are empty.
- A single current-feed trace does not establish historical reproducibility or fit of the midnight cutoff with MBTA publication patterns.

## Learning Progress

- The accepted snapshot decision records the author's reasoning about evidence availability, local-midnight cutoffs, coverage, identical ZIP content, and revisions.
- Understanding of source-row tracing and later reconciliation decisions still needs durable evidence as those parts are implemented.

## Next Recommended Work

### Human-led engineering

1. MUST — Continue Phase 1 by finishing the author-owned selector contract for accepted snapshot metadata: valid coverage, UTC receipts, exact cutoff, repeated content, and explicit unresolved outcomes. Stop when the accepted examples have clear results; bring any observed equal-time distinct-content tie to Mentor for a decision.
2. SHOULD — Define the smallest immutable archive/receipt interface and connect a selected hash and receipt to trace input and result. Stop at one reproducible versioned static trace; keep the current unversioned example honestly labeled.
3. STRETCH — Make Phase 0's trace accept a service date and record a short source-row explanation, then assess Phase 0 against its roadmap completion criteria.

### Verification and support work

- Tester (proposed): add focused selector cases for cutoff and daylight-saving boundaries, coverage boundaries/invalidity, repeated hashes, and unresolved outcomes; run the suite and report reproductions. Do not choose core semantics.
- Reviewer (proposed): independently assess the accepted ADR against selector, tests, and trace integration; report concrete gaps and assumptions. Review is not yet launched.
- Builder (proposed, after interface agreement): handle bounded archive metadata and parameterized path plumbing without choosing selection or revision semantics.
- Runtime support (proposed): declare an IANA timezone-data dependency for `C:\Python314\python.exe` and verify `America/New_York` loads there; Conda Python already works.
- State maintenance: this file reconciles `ac8c2ba` and the 2026-09-24 test run.

## Roadmap Impact

The accepted roadmap establishes Phase 0–20, with Phases 17–19 conditional on demonstrated need and a six-week core portfolio sequence. Current position is late Phase 0 / early Phase 1: static schedule behavior is implemented and tested within current scope, but Phase 0's parameterized input and formal acceptance remain; Phase 1 design is accepted and its selector is initial, without collection or versioned integration. Realtime archiving, feed health, reconciliation/reconstruction, replay, analytics, and operational hardening remain ahead. The roadmap is a scope baseline, not evidence that its six-week pace is already achieved.
