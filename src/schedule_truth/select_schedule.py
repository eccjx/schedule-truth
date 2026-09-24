from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

def select_schedule_snapshot(
    service_date: date,
    snapshots: list[dict],
    agency_timezone: str,
) -> dict:
    eligible = []
    local_midnight = datetime.combine(service_date, datetime.min.time()).replace(tzinfo=ZoneInfo(agency_timezone))
    utc_time = local_midnight.astimezone(timezone.utc)

    for snapshot in snapshots:
        if not snapshot['feed_start_date'] or not snapshot['feed_end_date']:
            continue
        if not snapshot['feed_start_date'] <= service_date <= snapshot['feed_end_date']:
            continue
        if snapshot['downloaded_at_utc'] > utc_time:
            continue
        eligible.append(snapshot)
        
    if not eligible:
        return {"status": "unresolved", "reason": "no eligible snapshot"}
    latest_snapshot = sorted(eligible, key=lambda x:x['downloaded_at_utc'], reverse=True)[0]




    return {"status": "selected", "snapshot": latest_snapshot}