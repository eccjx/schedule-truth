from datetime import date
from schedule_truth.gtfs_date import active_service_ids
from schedule_truth.gtfs_trips import (
    select_active_trips,
    group_trip_stop_times,
)


def scheduled_stop_times_for_date(
    service_date: date,
    calendar_rows: list[dict],
    exception_rows: list[dict],
    trip_rows: list[dict],
    stop_time_rows: list[dict],
) -> dict[str, list[dict]]:
    active_id = active_service_ids(service_date, calendar_rows, exception_rows)

    active_trips = select_active_trips(trip_rows, active_id)

    res = group_trip_stop_times(active_trips, stop_time_rows)

    return res