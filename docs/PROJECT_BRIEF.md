# Schedule Truth

## Project Goal

Schedule Truth is a production-style data engineering project that
reconstructs historical transit reliability by combining:

1. MBTA static GTFS schedules — what should happen.
2. MBTA GTFS-Realtime feeds — what appears to be happening.

The platform continuously archives ephemeral GTFS-Realtime data,
preserves historical schedule versions, and reconstructs actual
transit behavior such as lateness, missed service, bunching, and
feed-health events.

The primary purpose of the project is to demonstrate production-style
data engineering and data-platform skills for Data Engineer Intern and
Software Engineer — Data Platform Intern roles.

## Primary Data Source

MBTA, Boston.

Static:
- GTFS schedule ZIP

Realtime:
- Vehicle Positions
- Trip Updates
- Service Alerts

Realtime feeds use GTFS-Realtime protobuf.

## Core Engineering Questions

The project should answer:

- Which schedule version applied to a trip on a historical service date?
- What was supposed to happen?
- What realtime observations did we receive?
- How fresh/reliable were those observations?
- What most likely actually happened?
- How confident are we in that reconstruction?
- Can derived data be regenerated from immutable raw data?
- Can the pipeline be safely replayed without creating duplicates?

## Key Engineering Themes

- immutable raw storage
- event time vs feed time vs ingestion time
- versioned static schedules
- protobuf ingestion
- stale and missing data
- idempotency
- deterministic replay
- historical reconstruction
- data-quality monitoring
- observability
- analytical data modeling
- failure recovery

## Non-Goals

This is not primarily:

- a transit map
- a frontend project
- a dashboard project
- a machine-learning project

Visualizations may be added later, but the primary artifact is the
data platform itself.