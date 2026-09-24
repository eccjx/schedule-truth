from datetime import date
from pathlib import Path

from schedule_truth.gtfs_load import (
    load_calendar_rows,
    load_calendar_exception_rows,
    load_trip_rows,
    load_stop_time_rows,
)
from schedule_truth.gtfs_schedule import scheduled_stop_times_for_date

def main():
    feed_path =  Path("data/raw/MBTA_GTFS")
    service_date = date(2026, 9, 22)
    trip_id = "78942566"

    calendar_rows = load_calendar_rows(feed_path / "calendar.txt")
    calendar_dates_rows = load_calendar_exception_rows(feed_path / "calendar_dates.txt")
    trip_rows = load_trip_rows(feed_path / "trips.txt")
    stop_time_rows = load_stop_time_rows(feed_path / "stop_times.txt")

    schedule = scheduled_stop_times_for_date(service_date, calendar_rows, calendar_dates_rows, trip_rows, stop_time_rows)

    if trip_id in schedule:
        visits = schedule[trip_id]
        if not visits:
            print(f"Trip {trip_id} is scheduled, but no stop-time rows were found.")
            return
        starting_stop, ending_stop = visits[0]['stop_id'], visits[-1]['stop_id']
        starting_time, ending_time = visits[0]['departure_time'], visits[-1]['arrival_time']
        print(f"Trip {trip_id} has {len(visits)} visits, starting at stop {starting_stop} at {starting_time} and ending at stop {ending_stop} at {ending_time}.")
    else:
        print('The trip is not scheduled on this date.')
if __name__ == "__main__":
    main()