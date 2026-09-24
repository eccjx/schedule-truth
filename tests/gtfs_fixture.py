"""Small CSV feed shared by loader and trace tests; never uses downloaded data."""

import csv


TABLES = {
    "calendar.txt": (
        ["service_id", "monday", "tuesday", "wednesday", "thursday", "friday",
         "saturday", "sunday", "start_date", "end_date"],
        [["001", "1", "1", "1", "1", "1", "0", "0", "20260921", "20260927"]],
    ),
    "calendar_dates.txt": (
        ["service_id", "date", "exception_type"], [],
    ),
    "trips.txt": (
        ["trip_id", "route_id", "service_id"],
        [["78942566", "01", "001"], ["INACTIVE", "01", "002"]],
    ),
    "stop_times.txt": (
        ["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"],
        [["78942566", "LAST", "10", "25:10:00", "25:11:00"],
         ["INACTIVE", "OTHER", "1", "09:00:00", "09:01:00"],
         ["78942566", "FIRST", "2", "23:59:00", "24:00:00"]],
    ),
}


def write_table(folder, name, rows=None, encoding="utf-8-sig"):
    headers, defaults = TABLES[name]
    path = folder / name
    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(defaults if rows is None else rows)
    return path


def write_feed(folder):
    folder.mkdir(parents=True, exist_ok=True)
    for name in TABLES:
        write_table(folder, name)
