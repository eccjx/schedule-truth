# Current Project State

Last updated: 2026-09-18

## Current Phase

Initial GTFS time and service-date helpers are committed. Trip selection/grouping helpers and their tests are implemented in the working tree. No implementation milestone has been accepted or recorded.

## Completed

- Project goal and target architecture are documented in `PROJECT_BRIEF.md` and `ARCHITECTURE.md`. These are targets, not evidence of implemented pipeline behavior.
- Commit `12e9221` tracks the time and service-date helpers. This is an implementation checkpoint, not milestone acceptance.

## In Progress

- Untracked `src/schedule_truth/gtfs_trips.py` implements active-trip filtering and stop-time grouping.
- Untracked `tests/test_gtfs_trips.py` contains nine passing behavior tests for the trip helpers.
- The time/date helpers still need explicit contracts and automated coverage; the trip helper contract still needs author acceptance.

## Blocked

- None confirmed.

## Needs Verification

- No roadmap, implementation plan, or accepted first milestone exists. A time/date helper milestone remains a proposal for the author to decide.
- The time parser contract, including extended hours and malformed inputs, has not been documented or tested.
- The date module's calendar and exception semantics, input row types, and edge cases need author definition before completion can be assessed. The code expects parsed `date` values and numeric flags; raw GTFS files contain text fields.
- The trip tests deliberately leave malformed rows, duplicate identifiers/sequences, CSV coercion, and deep-copy guarantees unspecified.
- No repository evidence establishes the author's understanding or acceptance of GTFS time semantics.

## Test Status

- PASS: Direct `python -B -c` checks returned `45296` for `parse_gtfs_time('12:34:56')` and `90600` for `parse_gtfs_time('25:10:00')`.
- PASS: Direct `python -B -c` checks of `active_service_ids` with in-memory typed rows returned `{'WK'}` for normal service, `set()` after removal, and `{'EX'}` for an addition.
- PASS: `python -B -m unittest discover -s tests -p test_gtfs_trips.py -v` ran 9 tests successfully on Python 3.14.3. Covered filtering, ordering, grouping, empty inputs/groups, non-mutation, repeat calls, repeated stops, and composition for normalized rows.
- NOT RUN: Automated tests for the time/date helpers, trip-helper invalid-input cases, raw-feed integration, and lint. `pytest` and `ruff` were previously unavailable.
- NOT RUN: `python -m compileall -q src tests` could not create `__pycache__` directories due to `PermissionError`; successful unittest imports provide syntax/import evidence for the trip module and test file only.

## Important Findings

- The committed date helper checks the inclusive date range, named weekday flag, and matching exceptions; direct checks cover only three examples.
- The trip implementation and its tests are untracked. The passing result applies to the current working tree, not a committed revision.
- `README.md`, `DATA_MODEL.md`, `FAILURE_MODES.md`, and `LEARNING.md` are empty.
- The time/date source files are tracked in `12e9221`; no tests are tracked yet.
- `docs/ROADMAP.md`, Python project configuration, accepted decisions, and plans are absent.

## Current Technical Risks

- The time/date helpers have no automated test coverage; the repository has no defined package/dependency setup.
- GTFS times can exceed 24 hours; the parser contract should explicitly cover this and malformed inputs.
- The conversion boundary from raw GTFS text to the typed date rows expected by the helper is undefined.
- Trip grouping currently assumes normalized integer `stop_sequence` values; raw GTFS CSV values require an explicit conversion boundary.

## Learning Progress

Documented project concepts:
- The brief identifies schedule versioning, immutable raw data, replay, and feed health as central design concerns.

Needs deeper understanding:
- No repository evidence yet records the author's understanding of GTFS time semantics or the core reconciliation decisions.

## Next Recommended Work

1. MUST — Author: review and accept or revise the trip-helper behavior characterized by the nine tests, especially numeric `stop_sequence`, empty groups, input preservation, and unspecified malformed/duplicate cases. Acceptance: the intended contract is recorded and the tests still pass.
2. MUST — Author: add automated tests for the committed time/date helpers. Acceptance: normal, extended-hour, date-boundary, addition, removal, and agreed invalid-input cases pass using a recorded command.
3. SHOULD — Author: commit `gtfs_trips.py`, its tests, and the reconciled state after reviewing the diff. Acceptance: the working tree is clean and the test command passes against the commit.
4. SHOULD — Author: exercise the helpers with a small sample from the downloaded static GTFS files. Acceptance: raw text conversion is explicit and one known service date produces explainable ordered trip/stop results without changing the raw files.
5. STRETCH — Reviewer: independently assess the committed helpers and tests against the accepted contracts. Acceptance: concrete findings are resolved before the author accepts the milestone.

## Roadmap Impact

- `ROADMAP.md` is absent. A combined schedule-helper milestone is now a reasonable proposal, covering time parsing, service-date resolution, active-trip selection, and ordered stop times. It requires author acceptance and integration evidence before completion.
