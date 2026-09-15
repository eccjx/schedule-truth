# Target Architecture

## Core Data Flow

MBTA Static GTFS
        |
        v
Schedule Collector
        |
        v
Versioned Raw Schedule Storage
        |
        v
Normalized Schedule Tables
        |
        |
        +-----------------------+
                                |
MBTA GTFS-Realtime             |
                                |
Vehicle Positions              |
Trip Updates                   |
Alerts                         |
        |                       |
        v                       |
Realtime Collector             |
        |                       |
        +--> Immutable Raw      |
        |    Protobuf Storage   |
        |                       |
        v                       |
Normalized Realtime Records    |
        |                       |
        v                       |
Feed Health / Validation       |
        |                       |
        +-----------------------+
                 |
                 v
       Schedule Reconciliation
                 |
                 v
        Event Reconstruction
                 |
                 v
          Analytical Models
                 |
      +----------+----------+
      |          |          |
      v          v          v
  Lateness   Bunching   Feed Health


## Architectural Principles

1. Raw source data is immutable.
2. Derived datasets must be reproducible.
3. Historical data must resolve against the correct schedule version.
4. Event timestamps and ingestion timestamps remain distinct.
5. Missing realtime observations are not automatically treated as
   missing transit service.
6. Components should be independently testable.
7. Start simple; add distributed infrastructure only when justified.

## Possible Later Infrastructure

The following technologies may be introduced after the core pipeline
works:

- PostgreSQL
- Parquet
- object storage / S3 / MinIO
- dbt
- Docker
- Prometheus / Grafana
- Kafka / Redpanda
- PySpark

Kafka and Spark are not mandatory requirements. Their inclusion must
be justified by an actual architectural need or benchmark.