# Schedule Truth

Historical transit reliability from versioned schedules and archived realtime observations.

Schedule Truth is a Python data engineering project built around MBTA transit data. It preserves what was scheduled and what realtime feeds reported, with the goal of reconstructing trip and stop outcomes that can be traced back to their source evidence.

Realtime feeds change continually. A missing observation can mean a collection failure, a stale feed, or incomplete coverage. It does not, by itself, mean a bus failed to run. Schedule Truth keeps those distinctions explicit before attempting reliability metrics.

## Current capabilities

The project is under active development. The current implementation focuses on schedule history and raw realtime collection; historical reliability analytics are still planned.

| Component | Current implementation |
| --- | --- |
| Static GTFS helpers | Calendar exceptions, service-date selection, extended-hour time parsing, field normalization, and ordered stops per scheduled trip |
| Schedule archive | Retained ZIP bytes identified by SHA-256, content metadata, separate download receipts, and fetch-attempt records |
| Historical schedule selection | Coverage-aware selection using the latest eligible receipt available by the start of a service date in the MBTA timezone |
| Schedule tracing | Select an archived schedule and trace one trip's ordered stops |
| Vehicle Positions | Finite collection and a continuous Windows runner with request records and retained protobuf payloads |
| Trip Updates | A continuous Windows runner with compact request metadata, retained protobuf payloads, and integrity checks before payload reuse |
| Service Alerts | Planned |
| Feed health, reconciliation, and stop-event reconstruction | Planned |
| Analytical marts and historical replay of derived results | Planned |

See [current project state](docs/CURRENT_STATE.md) for detailed evidence and limitations, and the [roadmap](docs/ROADMAP.md) for future work.

## Design principles

- Preserve original source bytes and keep derived outputs separate.
- Distinguish content identity from collection identity: identical responses can still represent separate fetch attempts and receipts.
- Keep event time, feed creation time, and local collection time distinct.
- Resolve historical observations against an explicitly selected schedule version.
- Represent missing or uncertain evidence without claiming missing transit service.
- Build toward reproducible, idempotent processing and traceable analytical results.

The intended pipeline is:

```text
Static GTFS ZIPs                     GTFS-Realtime protobuf feeds
       |                                         |
Versioned schedule archive             Raw payloads + request records
       |                                         |
Schedule selection                     Normalization + feed health
       |                                         |
       +---------- Schedule reconciliation ------+
                              |
                   Stop-event reconstruction
                              |
             Reliability metrics and analytical tables
```

Collection and schedule selection are implemented. The downstream reconstruction and analytics stages are the target architecture.

## Getting started

Run the following from the repository root in PowerShell. The realtime collectors currently require **Windows** because their archive ownership and worker lifecycle controls use Windows APIs. The current development environment uses **Python 3.13**; broader platform and Python-version compatibility is not established.

Create a virtual environment and install the declared dependencies:

```powershell
python -m venv .venv
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install -r requirements.txt
& $python -m pip install tzdata
$env:PYTHONPATH = "$PWD\src"
```

`tzdata` supplies the timezone database needed for `America/New_York` when it is unavailable from the environment. The source tree is used through `PYTHONPATH`; an installable package is not configured yet. A fresh dependency installation has not yet been independently verified.

### Try a small offline example

```powershell
& $python -c "from schedule_truth.gtfs_time import parse_gtfs_time; print(parse_gtfs_time('25:10:00'))"
```

Expected output:

```text
90600
```

The parser preserves GTFS hours beyond 24 as seconds from the service-day origin instead of wrapping them to a time of day.

### Run the tests

```powershell
& $python -B -m unittest discover -s tests -q
```

The suite includes schedule/date behavior, archive integrity and selection, repeated payload handling, malformed responses, interrupted requests, response limits, and Windows process/deadline behavior. Some tests start local HTTP servers and child processes; they use synthetic data rather than requiring a live MBTA feed. Successful tests do not establish long-duration production reliability.

### Collect Vehicle Positions

This starts live network collection and writes to the chosen archive. Stop it with Ctrl+C.

```powershell
& $python -B -m schedule_truth.run_vehicle_positions --url https://cdn.mbta.com/realtime/VehiclePositions.pb --root data/raw/vehicle_positions
```

### Collect Trip Updates

Use a separate archive root for each feed. Run this in another configured PowerShell session if both collectors should operate at once:

```powershell
& $python -B -m schedule_truth.run_trip_updates --url https://cdn.mbta.com/realtime/TripUpdates.pb --root data/raw/trip_updates
```

Default completion-to-next-start delays are 15 seconds for Vehicle Positions and 30 seconds for Trip Updates. Both continuous runners default to a 30-second socket timeout, a 120-second network-reception deadline, and a 10 MiB response limit. Use `--help` to inspect their options.

Each poll gets a request record, including failed polls and repeated content. Complete response bytes are stored under a SHA-256 identity:

```text
data/raw/<feed>/
  requests/<request_id>.json
  payloads/<sha256>/response.pb
```

New Trip Updates records contain compact audit metadata. The retained protobuf contains the trip and stop fields; a reported stop time is not automatically a confirmed arrival or departure event.

See the [Vehicle Positions runner guide](docs/vehicle-positions-runner.md) and [Trip Updates runner guide](docs/trip-updates-runner.md) for shutdown, recovery, metadata, and integrity details.

### Use the static schedule API

Static collection currently exposes a Python function for one request per call. In a Python session using the environment above, supply a static GTFS ZIP endpoint:

```python
from pathlib import Path
from schedule_truth.collect_static_feed import collect_static_feed

result = collect_static_feed(
    url="YOUR_STATIC_GTFS_ZIP_URL",  # Replace with the source ZIP URL.
    archive_root=Path("data/raw/static_gtfs"),
)
print(result)
```

After collecting eligible history, use `schedule_truth.trace_schedule.trace_from_archive(archive_root, service_date, trip_id, "America/New_York")` to trace a trip. The service date is a `datetime.date`; the trip ID must come from the selected feed.

A ZIP downloaded today cannot establish what was known before an earlier service date. If no retained receipt meets the coverage and midnight-cutoff rules, selection returns an unresolved result. The [schedule-selection decision](docs/decisions/schedule-snapshot-selection.md) documents this policy.

## Limits to understand

- General power-loss and storage-failure recovery is not established; archive writes are not multi-file transactions.
- Realtime ownership excludes cooperating writers on the same Windows machine. It does not coordinate writers across machines.
- The reception deadline does not bound all parsing, filesystem work, or process cleanup.
- Existing extracted static CSVs are trusted. ZIP integrity verification does not detect changes to an already populated extraction cache.
- A successfully fetched and decoded snapshot does not establish feed freshness or healthy transit service.
- Automatic retention and archive deletion are not implemented; collection consumes disk space over time.
- Static periodic scheduling, sustained live runner operation, and clean deployment remain follow-up work.

Raw archives under `data/` are Git ignored and are not included in a source checkout.

## Repository guide

```text
src/schedule_truth/   Schedule helpers, archives, collectors, and runners
tests/               Unit, integration, and failure-case tests
docs/                Architecture, decisions, plans, and operating guides
requirements.txt     Realtime bindings and protobuf dependency declarations
```

- [Project brief](docs/PROJECT_BRIEF.md)
- [Target architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Known failure modes](docs/FAILURE_MODES.md)
- [Current implementation state](docs/CURRENT_STATE.md)
