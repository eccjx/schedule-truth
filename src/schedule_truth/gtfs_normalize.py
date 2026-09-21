from datetime import datetime
from schedule_truth.gtfs_time import parse_gtfs_time

def normalize_calendar_row(raw_row) -> dict:
    def date_checker(date_str):
        if len(date_str) != 8:
            return False
        for digit in date_str:
            if digit < "0" or digit > "9":
                return False
        return True
    
    weekday_list = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

    res = {}
    res['service_id'] = raw_row['service_id']

    for day in weekday_list:
        if raw_row[day] not in ("0", "1"):
            raise ValueError(f"Invalid {day}: {raw_row[day]!r}")
        res[day] = raw_row[day] == "1"

    if date_checker(raw_row['start_date']):
        try:
            res['start_date'] = datetime.strptime(raw_row['start_date'], "%Y%m%d").date()
        except ValueError as exc:
            raise ValueError(f"Invalid start_date: {raw_row['start_date']!r}") from exc
    else: 
        raise ValueError(f"Invalid start_date: {raw_row['start_date']!r}")


    if date_checker(raw_row['end_date']):
        try:
            res['end_date'] = datetime.strptime(raw_row['end_date'], "%Y%m%d").date()
        except ValueError as exc:
            raise ValueError(f"Invalid end_date: {raw_row['end_date']!r}") from exc
    else:  
        raise ValueError(f"Invalid end_date: {raw_row['end_date']!r}")
   
    return res


def normalize_calendar_exception_row(raw_row: dict[str, str]) -> dict:
    res = {}
    res['service_id'] = raw_row['service_id']

    if len(raw_row['date']) != 8:
        raise ValueError(f"Invalid date: {raw_row['date']!r}")
    for digit in raw_row['date']:
        if digit < "0" or digit > "9":
            raise ValueError(f"Invalid date: {raw_row['date']!r}")
    try:
        res['date'] = datetime.strptime(raw_row['date'], "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid date: {raw_row['date']!r}") from exc

    if raw_row['exception_type'] not in ("1", "2"):
        raise ValueError(f"Invalid exception_type: {raw_row['exception_type']!r}")
    res['exception_type'] = int(raw_row['exception_type'])

    return res


def normalize_trip_row(raw_row: dict[str, str]) -> dict:
    res = {}
    res['trip_id'] = raw_row['trip_id']
    res['route_id'] = raw_row['route_id']
    res['service_id'] = raw_row['service_id']

    return res


def normalize_stop_time_row(raw_row: dict[str, str]) -> dict:
    res = {}
    res['trip_id'] = raw_row['trip_id']
    res['stop_id'] = raw_row['stop_id']

    if raw_row['stop_sequence'] == "":
        raise ValueError(f"Invalid stop_sequence: {raw_row['stop_sequence']!r}")
    for digit in raw_row['stop_sequence']:
        if digit < "0" or digit > "9":
            raise ValueError(f"Invalid stop_sequence: {raw_row['stop_sequence']!r}")
    try:
        res['stop_sequence'] = int(raw_row['stop_sequence'])
    except ValueError as exc:
        raise ValueError(f"Invalid stop_sequence: {raw_row['stop_sequence']!r}") from exc

    if raw_row['arrival_time'] != "":
        try:
            parse_gtfs_time(raw_row['arrival_time'])
        except ValueError as exc:
            raise ValueError(f"Invalid arrival_time: {raw_row['arrival_time']!r}") from exc
    res['arrival_time'] = raw_row['arrival_time']

    if raw_row['departure_time'] != "":
        try:
            parse_gtfs_time(raw_row['departure_time'])
        except ValueError as exc:
            raise ValueError(f"Invalid departure_time: {raw_row['departure_time']!r}") from exc
    res['departure_time'] = raw_row['departure_time']

    return res
