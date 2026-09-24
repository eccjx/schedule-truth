# Schedule snapshot selection

Status: ACCEPTED by the author on 2026-09-24.

For an original report on service date D, select the latest archived GTFS ZIP received by 00:00 at the start of D in the MBTA agency timezone, provided `feed_info.txt` covers D. A missing or invalid feed coverage range makes that snapshot ineligible. Compare timezone-aware UTC receipt timestamps against local midnight converted to UTC. If no snapshot qualifies, report an unresolved schedule expectation. The first version assumes one collector and does not define selection among distinct contents with identical receipt timestamps.

Identify ZIP contents by SHA-256 hash and retain each download receipt separately. Retain the original result with its selected hash and receipt timestamp. A later result has a distinct revision ID linked to the original; show the newest revision by default while keeping earlier results retrievable.

The full examples, archive layout, and verification cases are in [the design detail](../plans/schedule-snapshot-selection.md). The rule is accepted but not implemented. The current 45-visit trace remains unversioned because its ZIP hash and receipt timestamp were not recorded.
