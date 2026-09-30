# Schedule snapshot selection

Status: ACCEPTED by the author on 2026-09-24, with the coverage-retention refinement accepted on 2026-09-28. Selection and local archiving are partially implemented; see CURRENT_STATE.md for verified feature status.

## Original report for service date D

Run one static-feed collector. Archive each downloaded ZIP with a precise UTC download timestamp and a hash of its ZIP bytes.

Use the latest archived static GTFS snapshot that:

1. Was downloaded no later than 00:00 at the start of D in the transit agency's timezone.
2. Contains schedule data covering D.

Latest means the eligible snapshot with the most recent download timestamp. Convert the agency-local start of D to an instant before comparing it with stored UTC timestamps. A snapshot downloaded exactly at the cutoff is eligible; one downloaded after it is not.

For the MBTA-only first version, read `agency_timezone` from the MBTA row in `agency.txt` (`America/New_York` in the current feed). Store each download receipt as a timezone-aware UTC timestamp with microsecond precision. Convert 00:00 on D in that agency timezone to UTC before comparing receipt timestamps. Do not use a fixed UTC offset; the timezone rules account for daylight-saving changes.

Repeated downloads with an identical ZIP content hash represent the same schedule content. Their download records still show when that content was available. The first version assumes one collector and does not define selection among distinct contents with identical receipt timestamps. Every derived schedule result records the chosen content and download evidence so the result can be reproduced. A later snapshot may produce a separately identified revision; it does not silently change the original report.

If no snapshot qualifies, mark the scheduled expectation unresolved and record why. A later snapshot may be used only through an explicitly labeled choice.

The cutoff is an evidence-availability rule. It does not assume that every trip starts after midnight. The rule's fit with MBTA publication patterns should be tested as the archive grows.

## Coverage of a service date

For this first version, use `feed_start_date` and `feed_end_date` from `feed_info.txt` as the snapshot's inclusive coverage range. A date inside that range is covered even when the schedule helpers find no active trips. A date outside the range makes the snapshot ineligible. If either coverage date is missing, blank, or invalid, treat coverage as unknown and do not select that snapshot for the original historical report. Do not infer coverage from calendar rows in this version.

Accepted archive refinement on 2026-09-28: retain the original ZIP and each receipt even when coverage is unknown. Persist both coverage dates as null and a nonempty `coverage_error`. Coverage strings must be exactly eight ASCII digits in YYYYMMDD form, parse to real dates, and form a non-reversed range. Retaining evidence does not make it eligible.

Accepted agency handling on 2026-09-29: choose the MBTA row rather than the first `agency.txt` row. For a missing MBTA row or missing/invalid MBTA timezone, retain the ZIP and receipt, store `America/New_York` as a configured fallback, and record source and reason. Duplicate MBTA rows and corrupt-ZIP persistence remain undecided. Automatic retained-ZIP integrity checking is deferred and prevents Phase 1 acceptance while the known mismatch remains; see `docs/FAILURE_MODES.md`.

## Archive identity and trace input

Use the SHA-256 hash of the original ZIP bytes as the schedule content identity. Retain the ZIP without modifying it and extract its CSV files into a directory named by that hash. Never overwrite that directory with files from another ZIP. If the extracted files are in doubt, recreate them from the retained ZIP.

Record each download separately with its precise UTC receipt timestamp and ZIP hash. Identical bytes downloaded at different times have one content identity and multiple receipt records. The original report cites the latest eligible receipt, even when an earlier receipt has the same hash.

A trace records both the selected ZIP hash and receipt timestamp. Its CSV loaders read from the extraction directory for that hash. The current `data/raw/MBTA_GTFS` trace has no recorded ZIP hash or receipt timestamp, so its 45-visit result is an unversioned demonstration; do not assign it invented archive metadata.

## Original reports and revisions

Give each original report a stable ID. Give each later result a distinct revision ID that points to the original report. Store the selected ZIP hash and receipt timestamp with every result, and do not overwrite earlier results. A current view shows the newest revision by default; earlier revisions remain retrievable with their source snapshots and prior values. A superseded result is historical evidence of what was reported, even when a newer revision is preferred for current analysis.

## Example

For an original report on September 22, snapshot A downloaded September 10 and snapshot B downloaded September 20 both qualify if each covers September 22. B wins. A snapshot downloaded September 22 at 00:30 in the agency timezone does not qualify for the original report; it could support a separately identified revision.

## Implementation boundary

The exact storage representation of report and revision IDs can be chosen during interface design without changing their meaning.

## Verification examples

- Eligible A and newer eligible B: choose B.
- B received after local midnight: choose A for the original report.
- Snapshot received exactly at local midnight: include it.
- No eligible snapshot: unresolved with a recorded reason.
- Later snapshot: original report retains its snapshot; any revised output has a separate identity.
- Identical-content repeated downloads: one schedule content identity, with eligible download evidence retained.
- Coverage-boundary cases: expected outcomes follow the coverage decision once accepted.
