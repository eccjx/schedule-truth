import csv
from pathlib import Path

from schedule_truth.gtfs_normalize import normalize_calendar_row
from schedule_truth.gtfs_normalize import normalize_calendar_exception_row
from schedule_truth.gtfs_normalize import normalize_trip_row
from schedule_truth.gtfs_normalize import normalize_stop_time_row

def load_calendar_rows(path):
    res = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            res.append(normalize_calendar_row(row))

    return res

def load_calendar_exception_rows(path):
    res = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            res.append(normalize_calendar_exception_row(row))

    return res

def load_trip_rows(path):
    res = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            res.append(normalize_trip_row(row))

    return res

def load_stop_time_rows(path):
    res = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            res.append(normalize_stop_time_row(row))

    return res