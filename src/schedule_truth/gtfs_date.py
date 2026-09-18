from datetime import date

def active_service_ids(service_date: date,calendar_rows: list[dict],exception_rows: list[dict]) -> set[str]:
    active = set()
    day_name = service_date.strftime("%A").lower()
    for row in calendar_rows:
        if row['start_date'] <= service_date <= row['end_date']:
            if row[day_name]:
                active.add(row['service_id'])
            

    for row in exception_rows:
        if row['date'] == service_date:
            if row['exception_type'] == 1:
                active.add(row['service_id'])
            if row['exception_type'] == 2:
                active.discard(row['service_id'])

    return active

