from datetime import date
from pathlib import Path

from schedule_truth.gtfs_load import (
    load_calendar_rows,
    load_calendar_exception_rows,
    load_trip_rows,
    load_stop_time_rows,
)
from schedule_truth.gtfs_schedule import scheduled_stop_times_for_date
from schedule_truth.select_schedule_snapshot import select_schedule_snapshot
from schedule_truth.archive_schedule import load_schedule_snapshots, extract_schedule_zip

def main(feed_path: Path, service_date: date, trip_id: str):


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

def trace_from_archive(archive_root: Path, service_date: date, trip_id: str, agency_timezone: str):
     snapshots = load_schedule_snapshots(archive_root)
     res = select_schedule_snapshot(service_date, snapshots, agency_timezone)
     if res['status'] == 'unresolved':
         print("There are no eligible snapshots.")
         return 
     else:
         zip_sha256 = res["snapshot"]['zip_sha256']
     feed_path = extract_schedule_zip(archive_root, zip_sha256)
     print(f"The selected path is {feed_path}, downloaded at {res['snapshot']['downloaded_at_utc']} utc.")
     main(feed_path, service_date, trip_id)

if __name__ == "__main__":
    main(Path("data/raw/MBTA_GTFS"), date(2026, 9, 22), "78942566")
