from collections import defaultdict


def select_active_trips(
    trip_rows: list[dict],
    active_service_ids: set[str],
) -> list[dict]:
    return [x for x in trip_rows if x['service_id'] in active_service_ids]

def group_trip_stop_times(
    selected_trips: list[dict],
    stop_time_rows: list[dict],
) -> dict[str, list[dict]]:
    
    res = defaultdict(list)
    for trip in selected_trips:
        res[trip['trip_id']] = []
    for row in stop_time_rows:
        if row['trip_id'] in res:
            res[row['trip_id']].append(row)
    for k, v in res.items():
        res[k] = sorted(v, key=lambda x: x['stop_sequence'])
    return res
