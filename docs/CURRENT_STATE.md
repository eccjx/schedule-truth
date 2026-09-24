# Current Project State

Last updated: 2026-09-24

## Current Phase

The schedule helpers and normalizers are committed. Working-tree CSV loaders and a trace script now run successfully against a downloaded MBTA feed. No implementation milestone has been accepted or recorded.

## Completed

- Project goal and target architecture are documented in `PROJECT_BRIEF.md` and `ARCHITECTURE.md`. These are targets, not evidence of implemented pipeline behavior.
- Commit `12e9221` tracks the time and service-date helpers. This is an implementation checkpoint, not milestone acceptance.
- Commit `18fbe60` tracks the trip helpers, nine trip-helper tests, and the schedule composition function.
- Commit `3ddd08e` tracks `gtfs_normalize.py`, the time/date/schedule and normalization tests, and ignores `data/raw`. The working tree was clean before this state reconciliation.

## In Progress

- Untracked `gtfs_load.py` reads four CSV tables through the normalizers; untracked `trace_schedule.py` traces one hardcoded service date and trip.
- The author reports explaining the real-feed trace with Mentor and handling the empty-visit case. Tester added focused loader/trace tests. Independent review and author milestone acceptance remain.
- The author and Mentor proposed a rule for choosing the static schedule snapshot for an original historical report; it is recorded in `docs/plans/schedule-snapshot-selection.md` and has not been accepted or implemented.

## Blocked

- None confirmed.

## Needs Verification

- No roadmap or accepted first milestone exists. The snapshot-selection plan is a proposal, not an accepted architecture decision.
- The time parser's current extended-hour and malformed-string behavior is tested but has not been recorded as an author-accepted contract.
- The normalizers convert raw string dates, flags, exception types, and stop sequences to the helper inputs. Their required-key, blank-ID, reversed-range, duplicate/conflict, and blank-time policies remain limited or unspecified.
- The trip tests deliberately leave malformed rows, duplicate identifiers/sequences, CSV coercion, and deep-copy guarantees unspecified.
- The schedule function returns a `defaultdict`, which is a `dict` subclass; the annotation alone is not a defect. Missing-key behavior remains a public-interface choice.
- The tests and bounded normalization changes include agent work; no repository evidence yet records the author's review and acceptance of consequential semantic assumptions.
- The author's source-row explanation was reported in chat but is not recorded in a repository artifact; mark that understanding NEEDS VERIFICATION until a short written trace or equivalent evidence exists.
- The proposal now specifies one collector, UTC receipt timestamps, SHA-256 ZIP identity, separate receipt records, content-based extraction directories, and reporting an actual same-time distinct-content ambiguity. Coverage, timestamp precision/timezone source, and report-revision identity still need resolution before implementation. The midnight cutoff has not been checked against MBTA publication patterns.

## Test Status

- PASS: Direct `python -B -c` checks returned `45296` for `parse_gtfs_time('12:34:56')` and `90600` for `parse_gtfs_time('25:10:00')`.
- PASS: Direct `python -B -c` checks of `active_service_ids` with in-memory typed rows returned `{'WK'}` for normal service, `set()` after removal, and `{'EX'}` for an addition.
- PASS: `python -B -m unittest discover -s tests -v` ran all 41 committed tests successfully on Python 3.14.3, including an in-memory raw-string normalization-to-schedule integration case.
- PASS: `python -B -m unittest discover -s tests -q` rerun on September 22: 41 tests passed. No dedicated loader/trace tests are present.
- PASS: `python -B -c "import sys; sys.path.insert(0,'src'); from schedule_truth.trace_schedule import main; main()"` ran against `data/raw/MBTA_GTFS`: trip `78942566` on `2026-09-22` has 45 visits, from stop `1747` at `19:10:00` to stop `797` at `20:03:00`.
- PASS: `python -B -m unittest discover -s tests -q` ran 55 tests on September 23 when Windows Temp was writable; 14 new loader/trace tests cover CSV decoding, normalization errors, empty visits, inactive trips, and source preservation.
- ENVIRONMENT FAILURE: The sandboxed run of the same command produced 40 temporary-directory access errors. It does not establish a code failure; the approved rerun passed.
- NOT RUN: Independent review, lint, and cases outside the current input contract. The successful actual-feed trace remains one feed/date/trip example.

## Important Findings

- Time tests cover integer seconds, extended hours, malformed components, widths/ranges, signs, whitespace, fractions, and non-ASCII digits.
- Date tests cover every weekday, inclusive ranges, disabled service, additions/removals, exception-only service, input preservation, and repeatability.
- Schedule tests exercise the public function with real helpers, including ordinary and exception service, ordered stops, inactive/orphan exclusion, empty results, input preservation, and repeatability.
- The trip implementation and tests are committed in `18fbe60`; the passing suite was rerun against that commit.
- `README.md`, `DATA_MODEL.md`, `FAILURE_MODES.md`, and `LEARNING.md` are empty.
- The time/date/schedule and normalization tests are tracked in `3ddd08e`; the full suite was rerun against that commit.
- The trace now distinguishes an active trip with no stop rows from a trip that is not scheduled; the dedicated test passes. This resolves the earlier empty-list finding.
- The trace hardcodes feed path, date, and trip; the CSV loaders do not add file/row context to normalization errors.
- `docs/ROADMAP.md`, Python project configuration, and accepted decisions are absent. A proposed snapshot-selection plan now exists.

## Current Technical Risks

- The repository has no defined package/dependency setup; tests currently modify `sys.path` to import the source tree.
- GTFS times can exceed 24 hours; the parser contract should explicitly cover this and malformed inputs.
- Actual CSV loading and schedule composition pass for one MBTA trace; broader feed behavior and a durable identity for the input snapshot remain unverified.
- The suite does not establish missing-field, reversed-range, conflicting-exception, duplicate, maximum-hour, non-string parser input, deep-copy, or exact `dict` versus `defaultdict` policies.

## Learning Progress

Documented project concepts:
- The brief identifies schedule versioning, immutable raw data, replay, and feed health as central design concerns.

Needs deeper understanding:
- No repository evidence yet records the author's understanding of GTFS time semantics or the core reconciliation decisions.

## Next Recommended Work

### Human-led engineering

1. MUST — Resolve the snapshot proposal's coverage rule, timestamp precision/timezone source, and report-revision identity; decide whether to accept the completed rule. Stop when covered no-service and uncovered dates are distinct and selection outcomes are explicit.
2. SHOULD — After accepting the rule, implement a small author-owned selector over archive metadata and connect the chosen ZIP hash to the existing loader/trace path. Stop when the September 22 A/B and no-eligible-snapshot cases have reproducible outcomes.
3. STRETCH — Record the source-row reasoning for the existing 45-visit trace so the reported understanding has durable evidence; keep it short and link it to the currently unversioned feed path.

### Verification and support work

- Loader/trace test support: 14 focused tests are implemented and passed; the test files remain untracked. Their scope excludes feed snapshot identity and several malformed-header/duplicate policies.
- Independent review (proposed): assess `3ddd08e` plus untracked loader, trace, and test files; report concrete findings and consequential choices before static-trace milestone acceptance.
- Mechanical support (proposed): after the author accepts a versioned-feed interface, add bounded archive metadata and parameterized feed/date/trip plumbing without choosing historical semantics.
- State maintenance: current test and trace evidence reconciled; proposed review and support have not been launched by this update.

## Roadmap Impact

- `ROADMAP.md` is absent. The proposed schedule-helper milestone now has 55 passing tests, a successful actual-feed trace, and explicit empty-visit handling. Independent review, durable source-row explanation, and author acceptance remain. Historical snapshot selection is documented as a proposal; whole-project estimates still need a bounded portfolio endpoint.
