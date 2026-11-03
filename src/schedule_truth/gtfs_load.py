import csv
from pathlib import Path

from schedule_truth.gtfs_normalize import normalize_calendar_row
from schedule_truth.gtfs_normalize import normalize_calendar_exception_row
from schedule_truth.gtfs_normalize import normalize_trip_row
from schedule_truth.gtfs_normalize import normalize_stop_time_row

def load_calendar_rows(path):
    """Read calendar.txt as CSV and return normalized weekly service rows."""
    res = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            res.append(normalize_calendar_row(row))

    return res

def load_calendar_exception_rows(path):
    """Read calendar_dates.txt as CSV and return normalized service exceptions."""
    res = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            res.append(normalize_calendar_exception_row(row))

    return res

def load_trip_rows(path):
    """Read trips.txt as CSV and return the trip, route, and service identifiers."""
    res = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            res.append(normalize_trip_row(row))

    return res

def load_stop_time_rows(path):
    """Read stop_times.txt as CSV and return validated, normalized stop-time rows."""
    res = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            res.append(normalize_stop_time_row(row))

    return res