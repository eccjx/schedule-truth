# Current Project State

Last updated: 2026-09-21

## Current Phase

The initial schedule-helper chain is committed: time parsing, active-service selection, active-trip filtering, ordered stop grouping, and date-level composition. No implementation milestone has been accepted or recorded.

## Completed

- Project goal and target architecture are documented in `PROJECT_BRIEF.md` and `ARCHITECTURE.md`. These are targets, not evidence of implemented pipeline behavior.
- Commit `12e9221` tracks the time and service-date helpers. This is an implementation checkpoint, not milestone acceptance.
- Commit `18fbe60` tracks the trip helpers, nine trip-helper tests, the schedule composition function, and the prior state update. The working tree was clean before this state reconciliation.

## In Progress

- Three untracked test files add automated coverage for the time, date, and public schedule helpers.
- The normalized-input behavior captured by all 27 tests still needs author review and acceptance before the milestone can be accepted.

## Blocked

- None confirmed.

## Needs Verification

- No roadmap, implementation plan, or accepted first milestone exists. A combined schedule-helper milestone remains a proposal for the author to decide.
- The time parser's current extended-hour and malformed-string behavior is tested but has not been recorded as an author-accepted contract.
- The date module's normalized behavior is tested, but its input contract still needs author acceptance. The code expects parsed `date` values and numeric flags; raw GTFS files contain text fields.
- The trip tests deliberately leave malformed rows, duplicate identifiers/sequences, CSV coercion, and deep-copy guarantees unspecified.
- The schedule function is annotated as returning `dict[str, list[dict]]` but currently returns the `defaultdict` produced by the grouping helper. Whether callers may rely on a plain `dict` needs a contract decision.
- The new tests are agent-generated regression checks; no repository evidence yet records the author's review and acceptance of their semantic assumptions.

## Test Status

- PASS: Direct `python -B -c` checks returned `45296` for `parse_gtfs_time('12:34:56')` and `90600` for `parse_gtfs_time('25:10:00')`.
- PASS: Direct `python -B -c` checks of `active_service_ids` with in-memory typed rows returned `{'WK'}` for normal service, `set()` after removal, and `{'EX'}` for an addition.
- PASS: `python -B -m unittest discover -s tests -v` ran all 27 tests successfully on Python 3.14.3: 9 committed trip tests and 18 untracked time/date/schedule tests.
- PASS: Python AST parsing with explicit UTF-8 decoding succeeded for all eight source/test files.
- NOT RUN: Raw-feed integration, lint, and cases intentionally left outside the normalized-input contract. `pytest` and `ruff` were last verified unavailable.

## Important Findings

- Time tests cover integer seconds, extended hours, malformed components, widths/ranges, signs, whitespace, fractions, and non-ASCII digits.
- Date tests cover every weekday, inclusive ranges, disabled service, additions/removals, exception-only service, input preservation, and repeatability.
- Schedule tests exercise the public function with real helpers, including ordinary and exception service, ordered stops, inactive/orphan exclusion, empty results, input preservation, and repeatability.
- The trip implementation and tests are committed in `18fbe60`; the passing suite was rerun against that commit.
- `README.md`, `DATA_MODEL.md`, `FAILURE_MODES.md`, and `LEARNING.md` are empty.
- The 18 new time/date/schedule tests are untracked, so their passing result applies to the working tree rather than a committed revision.
- `docs/ROADMAP.md`, Python project configuration, accepted decisions, and plans are absent.

## Current Technical Risks

- The repository has no defined package/dependency setup; tests currently modify `sys.path` to import the source tree.
- GTFS times can exceed 24 hours; the parser contract should explicitly cover this and malformed inputs.
- The conversion boundary from raw GTFS text to the typed date rows expected by the helper is undefined.
- Trip grouping currently assumes normalized integer `stop_sequence` values; raw GTFS CSV values require an explicit conversion boundary.
- The suite covers normalized in-memory rows but does not verify raw CSV conversion, malformed calendar rows, conflicting exceptions, duplicate policies, maximum GTFS hour range, non-string time inputs, deep-copy guarantees, or exact `dict` versus `defaultdict` behavior.

## Learning Progress

Documented project concepts:
- The brief identifies schedule versioning, immutable raw data, replay, and feed health as central design concerns.

Needs deeper understanding:
- No repository evidence yet records the author's understanding of GTFS time semantics or the core reconciliation decisions.

## Next Recommended Work

### Human-led engineering

1. MUST — Define the boundary between raw GTFS text and normalized helper inputs. Work through a small calendar and stop-time example, then record which layer converts dates and numeric fields and how invalid input should be handled. Stop when the contract is specific enough to implement and explain; unresolved choices may remain explicitly open.
2. SHOULD — Implement a small slice of that conversion using the agreed contract, then follow one service date through the schedule helper. Use a sample from downloaded static GTFS files if available. Stop when the path from source fields to ordered trip/stop results is understandable and raw files remain unchanged.
3. STRETCH — Resolve any specific semantic questions surfaced by verification, such as maximum hours, duplicate handling, or the public return type. Focus on decisions needed for the current slice; defer unrelated edge cases explicitly.

### Verification and support work

- Test coverage and execution: inspect the existing and new tests, compare their expectations with the documented contract as it becomes available, run relevant checks, and report reproducible failures. Present a short list of undecided semantic assumptions for the author instead of requiring a line-by-line test review.
- Independent review: assess the helper chain and tests against the recorded decisions after relevant fixes. Record the exact commit and any uncommitted files reviewed; report concrete findings and limitations.
- Mechanical support: prepare bounded setup or integration work that follows the agreed interfaces. Changes to protected semantics return to the author; committing changes requires the author's authorization.
- State maintenance: record verification evidence, remaining decisions, and milestone readiness. These tasks are queued recommendations; this planning update does not establish that they have run.

## Roadmap Impact

- `ROADMAP.md` is absent. The implemented chain now has broad normalized-input regression coverage, but test commitment, an explicit normalized-row contract, real-feed integration evidence, independent review, and author acceptance remain before milestone completion.
