# Schedule snapshot selection

Status: ACCEPTED by the author on 2026-09-24.

For an original report on service date D, select the latest archived GTFS ZIP received by 00:00 at the start of D in the MBTA agency timezone, provided `feed_info.txt` covers D. A missing or invalid feed coverage range makes that snapshot ineligible. Compare timezone-aware UTC receipt timestamps against local midnight converted to UTC. If no snapshot qualifies, report an unresolved schedule expectation. The first version assumes one collector and does not define selection among distinct contents with identical receipt timestamps.

Identify ZIP contents by SHA-256 hash and retain each download receipt separately. Retain the original result with its selected hash and receipt timestamp. A later result has a distinct revision ID linked to the original; show the newest revision by default while keeping earlier results retrievable.

Accepted refinement on 2026-09-28: when schedule coverage is missing or invalid, retain the original ZIP and its receipt as source evidence, persist both coverage dates as null, and record a nonempty coverage error. Such content remains ineligible for original historical schedule selection. A valid coverage date must contain exactly eight ASCII digits in YYYYMMDD form and represent a real date; a reversed range is invalid.

Accepted agency handling on 2026-09-29: use the MBTA row in `agency.txt`, even when another agency is listed first. If that row or its timezone is missing or invalid, retain the ZIP and receipt, use the configured `America/New_York` fallback, and record the fallback source and reason. Selection among duplicate MBTA rows is not defined. Corrupt-ZIP persistence policy remains unresolved. Automatic detection of changed retained ZIP bytes is explicitly deferred; see `docs/FAILURE_MODES.md` for the known integrity failure and its effect on Phase 1 acceptance.

The full examples, archive layout, and verification cases are in [the design detail](../plans/schedule-snapshot-selection.md). Selection, local archiving, and persisted archive-to-trace integration are implemented in the tested scope; HTTP collection and report/revision persistence are unfinished. The earlier 45-visit trace remains unversioned because its ZIP hash and receipt timestamp were not recorded.
