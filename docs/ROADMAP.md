# Schedule Truth — Project Roadmap

## Project Goal

Schedule Truth is a production-style data engineering project that reconstructs historical transit reliability by combining:

- **Static GTFS schedules** — what was supposed to happen
- **GTFS-Realtime feeds** — what appeared to be happening
- **Historical reconstruction logic** — what most likely actually happened

The system will continuously archive realtime MBTA transit data, preserve historical schedule versions, detect stale or unreliable source feeds, reconstruct stop/trip outcomes, and expose analytical datasets for reliability metrics such as lateness, missed service, and bus bunching.

The project is primarily intended to demonstrate skills relevant to:

- Data Engineer Intern
- Software Engineer — Data Platform Intern
- Data Platform / Infrastructure roles

---

# Guiding Engineering Principles

1. Raw source data is immutable.
2. Event time, feed time, and ingestion time must remain distinct.
3. Missing realtime observations do not automatically imply missing service.
4. Historical observations must resolve against the correct schedule version.
5. Derived datasets must be reproducible from raw source data.
6. Reprocessing must be idempotent.
7. Every derived fact should be traceable to source observations.
8. Start with simple architecture.
9. Kafka, Spark, and cloud infrastructure must be justified by actual needs.
10. Data correctness is more important than technology count.

---

# Phase 0 — GTFS Foundations

## Goal

Understand the GTFS data model before building infrastructure.

## Learn

- `routes.txt`
- `trips.txt`
- `stops.txt`
- `stop_times.txt`
- `calendar.txt`
- `calendar_dates.txt`
- `service_id`
- `trip_id`
- `stop_sequence`
- service dates
- GTFS times greater than `24:00:00`
- difference between a route and a trip

## Build

Create a small local Python program that:

1. Loads MBTA static GTFS data.
2. Accepts a service date.
3. Determines which services are active.
4. Returns the trips scheduled to operate on that date.

Example:

```text
Input:
2026-09-24

Output:
Trips scheduled to operate on 2026-09-24
```

## Core Questions

- What is the grain of a trip?
- How does GTFS determine whether a trip runs on a given date?
- How do `calendar.txt` and `calendar_dates.txt` interact?
- What does `25:30:00` mean in GTFS?

## Ownership

**HUMAN-LED**

The project author should implement the core service-date logic.

## Completion Criteria

- Can correctly resolve scheduled trips for a given service date.
- Handles calendar exceptions.
- Handles trips crossing midnight.
- Unit tests exist for service-date logic.

---

# Phase 1 — Static Schedule Collection and Versioning

## Goal

Continuously preserve MBTA schedule history instead of overwriting the latest GTFS ZIP.

## Build

Create a schedule collector that:

1. Downloads the current MBTA GTFS ZIP.
2. Validates the archive.
3. Calculates a SHA-256 hash.
4. Checks whether the artifact has already been seen.
5. Stores unseen versions immutably.
6. Registers schedule metadata.

Possible metadata:

```text
schedule_version_id
source_feed_version
downloaded_at
sha256
raw_path
valid_from
valid_to
```

## Learn

- immutable raw storage
- source versioning
- hashing
- reproducibility
- idempotent ingestion
- temporal data

## Core Question

> Which version of the schedule was valid when a historical trip occurred?

## Ownership

**HUMAN-LED**

Human:
- schedule-version semantics
- version-resolution logic

Agent-assisted:
- HTTP client
- retry logic
- ZIP validation
- CLI
- logging

## Completion Criteria

- Downloading the same GTFS ZIP twice does not create two versions.
- New source artifacts create new versions.
- Historical schedule files remain unchanged.
- Schedule metadata can be queried.

---

# Phase 2 — GTFS-Realtime Collector

## Goal

Continuously archive MBTA GTFS-Realtime data before it disappears.

## Sources

Collect:

- Vehicle Positions
- Trip Updates
- Service Alerts

## Build

A collector service that repeatedly:

```text
request feed
    ↓
record request metadata
    ↓
store exact protobuf payload
    ↓
register snapshot
```

Start with local filesystem storage.

Possible polling intervals:

```text
Vehicle Positions: ~15 seconds
Trip Updates:      ~30 seconds
Alerts:            ~60 seconds
```

These values can be adjusted later.

## Learn

- HTTP polling
- realtime data collection
- Protocol Buffers
- snapshot-oriented feeds
- retry/backoff
- collector reliability

## Ownership

**PAIR**

Human should understand how the collector works.

Agents may implement substantial boilerplate.

## Completion Criteria

- Collector runs continuously.
- Raw protobuf payloads are saved.
- Failed fetches are recorded.
- Duplicate snapshots can be identified.
- Collector restart does not corrupt existing history.

---

# Phase 3 — Immutable Raw Data Layer

## Goal

Ensure historical source data can always be replayed.

## Storage Structure

Example:

```text
data/
└── raw/
    ├── gtfs/
    │   └── ...
    │
    ├── vehicle_positions/
    │   └── service_date=YYYY-MM-DD/
    │       └── hour=HH/
    │
    ├── trip_updates/
    │   └── ...
    │
    └── alerts/
        └── ...
```

Realtime payloads may be compressed:

```text
.pb.gz
```

## Principle

Raw data represents:

> exactly what the external source gave us.

Raw files should never be "cleaned" or rewritten.

## Learn

- data lake layers
- immutable storage
- replayability
- lineage
- source-of-truth preservation

## Ownership

**PAIR**

## Completion Criteria

- Historical raw data is immutable.
- Every snapshot has a unique identifier.
- Every stored payload can be traced to ingestion metadata.

---

# Phase 4 — Ingestion Manifest

## Goal

Track the health and history of the ingestion process itself.

## Build

Create an ingestion manifest with fields such as:

```text
snapshot_id
feed_type
request_started_at
received_at
http_status
feed_header_timestamp
payload_size_bytes
raw_path
sha256
parse_status
error_message
```

## Why

The system must distinguish:

```text
No vehicle observation
```

from:

```text
Collector failed
```

from:

```text
Source feed was unavailable
```

from:

```text
Source feed was stale
```

## Learn

- operational metadata
- observability
- source lineage
- pipeline health

## Ownership

**PAIR**

## Completion Criteria

- Every fetch attempt creates an ingestion record.
- Failed requests are visible.
- Raw files can be traced back to requests.
- Duplicate snapshots can be identified.

---

# Phase 5 — Realtime Protobuf Parsing and Normalization

## Goal

Convert raw protobuf snapshots into queryable structured records.

## Build

Normalize:

### Vehicle Positions

Possible fields:

```text
snapshot_id
entity_id
vehicle_id
trip_id
route_id
direction_id
stop_id
stop_sequence
current_status
latitude
longitude
bearing
speed
vehicle_timestamp
feed_timestamp
ingested_at
```

### Trip Updates

Possible fields:

```text
snapshot_id
trip_id
route_id
start_date
schedule_relationship
stop_id
stop_sequence
arrival_time
arrival_delay
departure_time
departure_delay
feed_timestamp
ingested_at
```

### Alerts

Normalize relevant alert fields separately.

## Important Rule

Keep these separate:

```text
event_time
feed_time
ingestion_time
```

Do not silently collapse them into one timestamp.

## Learn

- Protocol Buffers
- schema design
- normalization
- nested-source parsing
- timestamp semantics

## Ownership

**PAIR / AGENT-ASSISTED**

Human should manually implement enough parsing to understand the structure.

Agents may handle repetitive mappings.

## Completion Criteria

- Raw protobuf can be parsed deterministically.
- Structured rows retain source snapshot IDs.
- Timestamp semantics remain explicit.
- Parser can run against archived files.

---

# Phase 6 — Feed Health and Data Quality

## Goal

Determine whether realtime observations are trustworthy.

## Build

Calculate metrics such as:

```text
feed_age_seconds
entity_age_seconds
fetch_success
entity_count
payload_size
parse_success
duplicate_snapshot
```

Create feed-health classifications such as:

```text
HEALTHY
STALE
PARTIAL
UNAVAILABLE
INVALID
```

## Example

```text
ingestion_time = 10:05:00
feed_time      = 10:04:52

feed_age = 8 seconds

=> HEALTHY
```

Versus:

```text
ingestion_time = 10:05:00
feed_time      = 10:00:00

feed_age = 300 seconds

=> STALE
```

## Key Principle

A successful HTTP request does not necessarily mean the source data is fresh.

## Learn

- data quality engineering
- observability
- source freshness
- missing-data semantics
- operational reliability

## Ownership

**HUMAN-LED**

The project author should design the health semantics.

## Completion Criteria

- Feed health is recorded for every snapshot.
- Stale feeds can be identified.
- HTTP/source failures are distinguishable.
- Entity freshness can be measured separately from feed freshness.

---

# Phase 7 — Historical Schedule Resolution

## Goal

Determine which schedule definition applies to each realtime observation.

## Build

Given:

```text
service_date
trip_id
stop_sequence
```

resolve:

```text
schedule_version
route
scheduled_trip
scheduled_stop
scheduled_arrival
scheduled_departure
```

## Core Problem

A schedule downloaded today must not rewrite the historical meaning of a trip that occurred weeks earlier.

## Learn

- temporal joins
- slowly changing data
- historical dimensions
- effective-date modeling
- reference-data versioning

## Ownership

**HUMAN-LED**

This is one of the project's most important learning modules.

## Completion Criteria

- Historical observations resolve to the correct schedule version.
- Version changes do not alter historical results.
- Unmatched trip IDs are explicitly recorded.

---

# Phase 8 — Stop Event Reconstruction

## Goal

Infer what most likely happened at each scheduled stop.

## Example

Realtime observations:

```text
08:31:54
stop_sequence=8
IN_TRANSIT_TO

08:32:08
stop_sequence=8
STOPPED_AT

08:32:21
stop_sequence=9
IN_TRANSIT_TO
```

Possible inference:

```text
observed_arrival = 08:32:08
observation_method = STOPPED_AT
confidence = HIGH
```

For incomplete observations:

```text
observation_method = SEQUENCE_TRANSITION
confidence = MEDIUM
```

## Build

Create an event-reconstruction engine that outputs fields such as:

```text
service_date
trip_id
stop_sequence
scheduled_arrival
observed_arrival
observed_departure
observation_method
confidence
source_snapshot_ids
```

## Learn

- stateful reasoning
- event reconstruction
- imperfect-data inference
- algorithm design
- confidence modeling

## Ownership

**STRONGLY HUMAN-LED**

This should be one of the main components the project author personally implements.

## Completion Criteria

- High-confidence stop arrivals can be reconstructed.
- Missing observations do not automatically produce false events.
- Reconstruction methods are explicit.
- Source observations are traceable.
- Adversarial tests exist.

---

# Phase 9 — Trip Outcome Classification

## Goal

Determine what happened to each scheduled trip.

## Possible Outcomes

```text
COMPLETED
PARTIALLY_OBSERVED
CANCELED
LIKELY_MISSED
UNKNOWN_DUE_TO_FEED_OUTAGE
```

## Important Principle

Do not implement:

```text
scheduled trip
-
observed trip
=
missed trip
```

without considering feed health.

## Learn

- missing-data interpretation
- operational data modeling
- classification rules
- uncertainty

## Ownership

**HUMAN-LED**

## Completion Criteria

- Canceled and missing trips are distinguished.
- Feed outages prevent false "missed trip" classifications.
- Partial observation is represented explicitly.

---

# Phase 10 — Analytical Warehouse and dbt

## Goal

Turn reconstructed operational events into reliable analytical datasets.

## Build

Possible dbt structure:

```text
staging/
    stg_gtfs_trips
    stg_gtfs_stop_times
    stg_vehicle_positions
    stg_trip_updates

intermediate/
    int_trip_schedule
    int_observed_stop_events
    int_trip_reconstruction

marts/
    fact_stop_adherence
    fact_trip_reliability
    fact_feed_health
    fact_bunching_events

    dim_route
    dim_stop
    dim_schedule_version
```

## Central Fact Grain

`fact_stop_adherence`:

> One scheduled trip × one stop × one service date.

## Add Tests

Examples:

```text
unique
not_null
relationships
accepted_values
custom business-rule tests
```

## Learn

- dimensional modeling
- dbt
- SQL transformations
- data contracts
- warehouse testing

## Ownership

**PAIR**

## Completion Criteria

- Models build deterministically.
- Fact-table grain is explicit.
- dbt tests pass.
- Analytics can trace back to reconstructed source events.

---

# Phase 11 — Reliability Metrics and Bus Bunching

## Goal

Produce useful domain-level outputs.

## Build

Metrics such as:

- scheduled vs observed arrival
- stop lateness
- route reliability
- headway deviation
- bus bunching
- missed service
- feed reliability

## Bunching Example

Scheduled:

```text
Bus A ----10m---- Bus B ----10m---- Bus C
```

Observed:

```text
Bus A --------18m-------- Bus B --2m-- Bus C
```

Calculate actual headways using window functions.

## Learn

- SQL window functions
- time-series analytics
- analytical metric design

## Ownership

**PAIR**

## Completion Criteria

- At least several meaningful analytical marts exist.
- Metrics are explainable to nontechnical users.
- Metrics depend on reconstructed data rather than raw snapshots.

---

# Phase 12 — Replay and Backfill

## Goal

Allow derived data to be rebuilt after code changes or bugs.

## Build

A command similar to:

```bash
schedule-truth replay \
  --from 2026-09-01 \
  --to 2026-09-20
```

The replay system should:

```text
read archived raw data
        ↓
reparse
        ↓
revalidate
        ↓
reconstruct
        ↓
rewrite derived state safely
```

## Learn

- backfills
- historical reprocessing
- deterministic transformations
- recovery from bugs

## Ownership

**HUMAN-LED**

## Completion Criteria

- Historical data can be regenerated without contacting MBTA.
- Parser/reconstruction fixes can be applied to old raw data.
- Replay is deterministic.

---

# Phase 13 — Idempotency

## Goal

Make repeated processing safe.

## Requirement

Running the same replay twice should produce:

```text
same logical result
```

not:

```text
duplicated rows
```

## Design

Clearly distinguish:

### Ingestion identity

Example:

```text
snapshot_id
entity_id
```

### Business/event identity

Example:

```text
service_date
trip_id
stop_sequence
event_type
```

## Learn

- business keys
- deduplication
- safe retries
- idempotent writes
- distributed-system correctness

## Ownership

**HUMAN-LED**

## Completion Criteria

- Replaying identical input twice produces identical output.
- Duplicate source snapshots do not duplicate facts.
- Tests prove idempotent behavior.

---

# Phase 14 — Automated Testing and Failure Injection

## Goal

Validate the system under real failure conditions.

## Test Scenarios

Include:

- duplicate snapshot
- stale feed
- out-of-order event
- missing observation
- collector outage
- HTTP timeout
- malformed protobuf
- corrupt GTFS ZIP
- new schedule version
- unknown trip ID
- canceled trip
- trip crossing midnight
- GTFS time greater than 24 hours
- replaying identical data
- parser bug followed by historical replay

## Learn

- unit testing
- integration testing
- property/edge-case thinking
- failure-mode analysis

## Ownership

**TEST AGENT + HUMAN**

Agents should aggressively generate adversarial cases.

Human should understand every important failure discovered.

## Completion Criteria

- Major invariants have tests.
- Regressions are reproducible.
- Known failure modes are documented.

---

# Phase 15 — Observability

## Goal

Know when the pipeline itself is unhealthy.

## Possible Metrics

```text
collector_requests_total
collector_errors_total
feed_age_seconds
payload_size_bytes
vehicle_observations_total
trip_updates_total
parse_failures_total
unmatched_trip_rate
processing_duration_seconds
replay_duration_seconds
```

## Tools

Possible:

- Prometheus
- Grafana

## Learn

- monitoring
- metrics
- service health
- operational debugging

## Ownership

**AGENT-ASSISTED**

## Completion Criteria

- Pipeline health can be inspected.
- Feed freshness is visible.
- Collector and parser errors are measurable.
- Operational failures can be diagnosed.

---

# Phase 16 — Containerization and CI

## Goal

Make the project reproducible and maintainable.

## Add

- Docker
- Docker Compose
- GitHub Actions
- linting
- unit tests
- integration tests
- dbt tests

Desired developer experience:

```bash
docker compose up
```

should start the required local services.

## Learn

- software delivery
- CI/CD
- reproducible environments
- engineering hygiene

## Ownership

**MOSTLY DELEGATED**

The project author should understand the system but does not need to hand-write every configuration file.

## Completion Criteria

- Fresh checkout can be started predictably.
- CI validates every PR.
- Tests run automatically.

---

# Phase 17 — Evaluate Kafka / Redpanda

## Goal

Determine whether asynchronous messaging improves the architecture.

## Do Not Add Kafka Automatically

Initial architecture may remain:

```text
collector
    ↓
raw storage
    ↓
processor
```

Introduce messaging only if there is a clear need such as:

- collection and parsing need independent scaling
- processing crashes must not affect collection
- multiple consumers need new-snapshot notifications
- asynchronous processing improves reliability

Possible later architecture:

```text
MBTA
  ↓
Collector
  ├──────→ Raw Object Storage
  │
  └──────→ snapshot_ingested event
                   ↓
             Kafka/Redpanda
                   ↓
                Consumers
```

## Learn

- message brokers
- producer/consumer design
- decoupling
- delivery semantics
- consumer groups

## Ownership

**PAIR / OPTIONAL**

## Completion Criteria

Kafka is introduced only if its benefits can be explained and demonstrated.

---

# Phase 18 — Evaluate Spark

## Goal

Determine whether distributed processing improves historical replay or batch processing.

## Experiment

Benchmark:

```text
local Python / Polars
vs
PySpark
```

on a large archived dataset.

Measure:

- records processed
- execution time
- throughput
- memory
- CPU
- operational complexity

## Decision

If Spark helps substantially, adopt it for large backfills.

If it does not, document why the simpler approach remains preferable.

## Learn

- distributed computation
- Spark execution
- benchmarking
- engineering tradeoffs

## Ownership

**PAIR / OPTIONAL**

---

# Phase 19 — Cloud Deployment

## Goal

Move selected production components beyond the local laptop.

Possible components:

```text
raw data       → S3
metadata DB    → managed PostgreSQL
compute        → container service / VM
monitoring     → cloud or self-hosted stack
```

Infrastructure may be managed with Terraform.

## Learn

- cloud storage
- IAM
- infrastructure as code
- deployment
- cost-aware system design

## Ownership

**AGENT-ASSISTED**

## Completion Criteria

- At least the long-running collector can operate reliably outside a development laptop.
- Cloud costs remain controlled.
- Infrastructure is reproducible.

---

# Phase 20 — Portfolio and Interview Hardening

## Goal

Turn the working system into a compelling public engineering artifact.

## README Should Explain

1. The problem.
2. Why realtime history must be collected continuously.
3. Architecture.
4. Data model.
5. Source semantics.
6. Failure modes.
7. Schedule-version strategy.
8. Feed-health strategy.
9. Replay/idempotency.
10. Benchmarks.
11. Testing.
12. Major engineering tradeoffs.

## Include Demonstrations

Examples:

### Feed outage

```text
feed stops updating
       ↓
feed_age rises
       ↓
health => STALE
       ↓
trip absence not classified as missed
```

### Replay

```text
parser bug discovered
       ↓
parser fixed
       ↓
historical raw snapshots replayed
       ↓
corrected analytical facts
```

### Idempotency

```text
same replay executed twice
       ↓
final logical dataset unchanged
```

## Interview Preparation

For every major subsystem, be able to explain:

- Why does this exist?
- What problem does it solve?
- What alternatives were considered?
- What can fail?
- How is failure detected?
- How is correctness tested?
- How does replay work?
- What would change at 10× scale?

---

# Recommended Development Order

The project should approximately follow:

```text
Phase 0
GTFS foundations

    ↓

Phase 1
Static schedule versioning

    ↓

Phase 2–4
Realtime collection + immutable storage + manifest

    ↓

Phase 5–6
Normalization + feed health

    ↓

Phase 7–9
Schedule reconciliation + reconstruction + trip outcomes

    ↓

Phase 10–11
dbt warehouse + analytics

    ↓

Phase 12–14
Replay + idempotency + failure testing

    ↓

Phase 15–16
Observability + CI/containerization

    ↓

Phase 17–19
Kafka / Spark / cloud if justified

    ↓

Phase 20
Portfolio + interview hardening
```

---

# Suggested Six-Week Milestones

## Week 1 — Understand and Preserve the Schedule

Complete:

- Phase 0
- most of Phase 1

Deliverable:

> Versioned MBTA schedule ingestion with correct service-date resolution.

---

## Week 2 — Start Building Unique Realtime History

Complete:

- Phase 2
- Phase 3
- Phase 4

Deliverable:

> Continuously running GTFS-Realtime collector preserving immutable source snapshots.

Important:

**Start this as early as possible.**

Realtime history that was never collected cannot reliably be recreated later.

---

## Week 3 — Normalize and Assess Source Reliability

Complete:

- Phase 5
- Phase 6

Deliverable:

> Queryable realtime observations plus feed-health monitoring.

---

## Week 4 — Reconstruct Historical Transit Behavior

Complete:

- Phase 7
- Phase 8
- Phase 9

Deliverable:

> Scheduled vs observed stop/trip reconstruction.

This is the project's deepest engineering week.

---

## Week 5 — Build the Data Product

Complete:

- Phase 10
- Phase 11
- begin Phase 12–13

Deliverable:

> Tested analytical marts for adherence, reliability, feed health, and bunching.

---

## Week 6 — Make It Production-Style

Complete:

- replay
- idempotency
- failure tests
- observability
- CI
- Docker
- documentation
- benchmarks

Deliverable:

> Public portfolio-quality repository that can survive technical interview questioning.

Kafka, Spark, and substantial cloud infrastructure may continue afterward if they are justified.

---

# Human vs Agent Ownership Summary

## HUMAN-LED

You should deeply understand and personally contribute to:

- GTFS service-date logic
- schedule-version semantics
- feed-health semantics
- temporal schedule reconciliation
- stop-event reconstruction
- trip outcome rules
- idempotency strategy
- replay semantics

## PAIR WITH CODEX

Good areas for guided implementation:

- GTFS parsing
- protobuf parsing
- normalized schemas
- database access
- dbt models
- analytical SQL
- metrics
- Kafka/Spark experiments

## DELEGATE HEAVILY

Good areas for automation:

- HTTP boilerplate
- CLI plumbing
- logging setup
- Docker configuration
- CI configuration
- Terraform boilerplate
- Grafana provisioning
- repetitive field mappings
- fixture generation

---

# Final Success Criteria

Schedule Truth is complete when you can demonstrate:

1. A historical MBTA schedule is preserved with versions.
2. GTFS-Realtime snapshots are continuously archived.
3. Raw observations are immutable.
4. Source/feed health is explicitly modeled.
5. Realtime observations resolve against the correct historical schedule.
6. Stop and trip outcomes can be reconstructed.
7. Missing observations are treated carefully.
8. Analytical marts expose meaningful reliability metrics.
9. Historical data can be replayed after code changes.
10. Replay is idempotent.
11. Failure scenarios are tested.
12. Pipeline health is observable.
13. The project can be reproduced from a clean environment.
14. Every major design decision can be defended in an interview.
15. Optional infrastructure such as Kafka and Spark exists only where justified.

The end product should demonstrate not simply that you can move data, but that you can reason about **historical correctness, unreliable realtime sources, reproducibility, failure recovery, and operational data systems**.