# Schedule snapshot selection

Status: ACCEPTED by the author on 2026-09-24, with the coverage-retention refinement accepted on 2026-09-28. Selection, local archiving, one-request HTTP collection, and persisted tracing are verified; Phase 1's local collection/versioning scope was author accepted on 2026-09-30. Persistent reports/revisions and operational hardening remain unfinished; see CURRENT_STATE.md for verified feature status.

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

Accepted agency handling on 2026-09-29: choose the MBTA row rather than the first `agency.txt` row. For a missing MBTA row or missing/invalid MBTA timezone, retain the ZIP and receipt, store `America/New_York` as a configured fallback, and record source and reason. Duplicate MBTA rows remain undecided. Retained ZIP hash verification was implemented on 2026-09-30; extracted files are not independently verified. See `docs/FAILURE_MODES.md`.

## Static-feed fetch attempts and invalid downloads

Accepted by the author on 2026-09-30 for the planned MBTA HTTP collector. Record a separate attempt for every HTTP request, including each retry. Create its identity and record the request URL and UTC attempt time before fetching; finish it with an outcome and error or a link to received content. A failed request that yields no bytes has an attempt/error record but no content hash or download receipt.

If bytes are received but cannot be opened as a valid ZIP, retain those exact bytes under their SHA-256 hash and link them to the failed attempt with the ZIP-validation error. Such bytes have no selectable schedule content metadata or successful download receipt and must not be used for tracing. A validated ZIP follows the normal archive path: content metadata and a distinct receipt linked to the successful attempt. Repeated requests remain separate attempts even if they receive identical bytes.

The one-request collector's attempt-file format and normal write ordering are implemented and tested. Crash-recovery behavior remains undecided and unverified; the writes are not a transaction. This policy does not redefine the existing behavior for a valid ZIP with missing coverage or invalid agency metadata. Retained ZIP hash mismatch is now detected before extraction; automatic repair remains undefined.

Accepted refinement on 2026-09-30: if an HTTP request returns an error status or transport error together with bytes that happen to form a readable ZIP, the request still failed. Retain the exact bytes, their hash, request error, and attempt record for investigation, but create no successful receipt and do not make that ZIP selectable. The readability of the response body does not override the failed request outcome.

## MBTA timezone consistency in archived traces

Accepted by the author on 2026-09-30: this first version is MBTA-only and uses the configured `America/New_York` timezone to determine the original-report local-midnight cutoff. A caller must not silently substitute a different timezone. After selection, the chosen archive's persisted `agency_timezone` must agree with the configured MBTA timezone; a mismatch is an explicit trace error, not a reason to silently change the cutoff or select another archive. The selected archive's timezone source and any fallback reason remain available in its content metadata.

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
