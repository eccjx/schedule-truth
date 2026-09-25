from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

def select_schedule_snapshot(
    service_date: date,
    snapshots: list[dict],
    agency_timezone: str,
) -> dict:
    def utc_check(dt) -> bool:
       return dt.tzinfo is None or dt.tzinfo.utcoffset(dt).total_seconds() != 0


    eligible = []
    if not agency_timezone:
        raise ValueError("No input timezone.")

    local_midnight = datetime.combine(service_date, datetime.min.time()).replace(tzinfo=ZoneInfo(agency_timezone))
    utc_time = local_midnight.astimezone(timezone.utc)

    for snapshot in snapshots:
        if type(snapshot.get('feed_start_date')) is not date or type(snapshot.get('feed_end_date')) is not date:
            continue
        if not snapshot['feed_start_date'] or not snapshot['feed_end_date']:
            continue
        if snapshot['feed_start_date'] > snapshot['feed_end_date']:
            continue
        if not snapshot['feed_start_date'] <= service_date <= snapshot['feed_end_date']:
            continue
        if type(snapshot['downloaded_at_utc']) is not datetime:
            raise ValueError(f"Wrong date type: {snapshot['downloaded_at_utc']}.")
        if utc_check(snapshot['downloaded_at_utc']):
            raise ValueError(f"Wrong time zone or empty time zone.")
        if snapshot['downloaded_at_utc'] > utc_time:
            continue
        eligible.append(snapshot)
        
    if not eligible:
        return {"status": "unresolved", "reason": "no eligible snapshot"}
    latest_snapshot = sorted(eligible, key=lambda x:x['downloaded_at_utc'], reverse=True)[0]




    return {"status": "selected", "snapshot": latest_snapshot}
