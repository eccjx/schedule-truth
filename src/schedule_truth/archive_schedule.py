from datetime import datetime, date
from pathlib import Path
import hashlib
from uuid import uuid4
import json
import csv
import io
import zipfile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

def archive_schedule_zip(
    zip_path: Path,
    archive_root: Path,
    downloaded_at_utc: datetime,
) -> dict:
    def utc_check(dt) -> bool:
           offset = dt.utcoffset()
           return offset is None or offset.total_seconds() != 0    
    if utc_check(downloaded_at_utc):
         raise ValueError("The downloaded time is not utc.")
    
    zip_bytes = zip_path.read_bytes()
    zip_sha256 = hashlib.sha256(zip_bytes).hexdigest()
    destination_path = archive_root / zip_sha256 / "original.zip"
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if not destination_path.exists():
            destination_path.write_bytes(zip_bytes)
        
    # Content
    feed_start_date = None
    feed_end_date = None
    coverage_error = None
    with zipfile.ZipFile(zip_path) as archive:
        try:
            with archive.open("feed_info.txt") as member:
                text = io.TextIOWrapper(member, encoding="utf-8-sig")
                feed_info_rows = list(csv.DictReader(text))
                feed_start_date_str = feed_info_rows[0]['feed_start_date']
                feed_end_date_str = feed_info_rows[0]['feed_end_date']
                if not feed_start_date_str or not feed_end_date_str:
                    coverage_error = "missing coverage"
                else:
                    for value in (feed_start_date_str, feed_end_date_str):
                        if len(value) != 8 or not value.isascii() or not value.isdigit():
                            raise ValueError("Coverage dates must contain exactly eight ASCII digits.")
                    feed_start_date = datetime.strptime(feed_info_rows[0]['feed_start_date'], "%Y%m%d").date()
                    feed_end_date = datetime.strptime(feed_info_rows[0]['feed_end_date'], "%Y%m%d").date()
                    if feed_start_date > feed_end_date:
                        feed_start_date = None
                        feed_end_date = None
                        coverage_error = "start date is greater than end date"
        except (KeyError, IndexError, ValueError, csv.Error) as error:
            feed_start_date = None
            feed_end_date = None
            coverage_error = f"missing or invalid coverage: {error}"
        agency_timezone = "America/New_York"
        agency_timezone_source = "configured_fallback"
        agency_timezone_error = None

        try:
            with archive.open("agency.txt") as member:
                text = io.TextIOWrapper(member, encoding="utf-8-sig")
                agency_rows = list(csv.DictReader(text))
                mbta_row = next(
                    (row for row in agency_rows if row.get("agency_name") == "MBTA"),
                    None,
                )
                if mbta_row is None:
                    raise ValueError("MBTA agency row is missing")

                supplied_timezone = mbta_row.get("agency_timezone")
                if not supplied_timezone:
                    raise ValueError("blank MBTA agency timezone")

                ZoneInfo(supplied_timezone)
                agency_timezone = supplied_timezone
                agency_timezone_source = "agency.txt"
        except (KeyError, IndexError, ValueError, ZoneInfoNotFoundError) as error:
            agency_timezone_error = str(error)
        
    content = {
            "zip_sha256": zip_sha256,
            "zip_path": destination_path,
            "feed_start_date": feed_start_date,
            "feed_end_date": feed_end_date,
            "agency_timezone": agency_timezone,
            "agency_timezone_source": agency_timezone_source,
            "agency_timezone_error": agency_timezone_error,
        }
    if coverage_error:
         content['coverage_error'] = coverage_error
    content_path = archive_root / zip_sha256 / "content.json"
    content_path.parent.mkdir(parents=True, exist_ok=True)

    content_json = content.copy()
    content_json["zip_path"] = str(content["zip_path"])
    content_json["feed_start_date"] = (
    feed_start_date.isoformat() if feed_start_date is not None else None
)
    content_json["feed_end_date"] = (
    feed_end_date.isoformat() if feed_end_date is not None else None
)
    if not content_path.exists():
        with open(content_path, "w", encoding="utf-8") as file:
            json.dump(content_json, file, indent=4)
            
    # Receipt
    receipt_id = uuid4().hex
    receipt = {
    "receipt_id": receipt_id,
    "zip_sha256": zip_sha256,
    "downloaded_at_utc": downloaded_at_utc,
}
    receipt_path = archive_root / "receipts" / f"{receipt_id}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_json = receipt.copy()
    receipt_json['downloaded_at_utc'] = receipt["downloaded_at_utc"].isoformat()
    with open(receipt_path, "w", encoding="utf-8") as file:
        json.dump(receipt_json, file, indent=4)

    
    return {"content": content, "receipt": receipt}


def load_schedule_snapshots(archive_root: Path) -> list[dict]:
    res = []
    for receipt_path in (archive_root / "receipts").glob("*.json"):
        with receipt_path.open("r", encoding="utf-8") as file:
            receipt = json.load(file)
        zip_sha256 = receipt['zip_sha256']
        content_path = archive_root / zip_sha256 / "content.json"
        with content_path.open("r", encoding="utf-8") as file:
            content = json.load(file)
        if content['zip_sha256'] != zip_sha256:
            raise ValueError(f"Content hash does not match receipt: {receipt_path}")

        snapshot = content.copy()
        snapshot['zip_path'] = Path(content['zip_path'])
        if content['feed_start_date'] is not None:
            snapshot['feed_start_date'] = date.fromisoformat(content['feed_start_date'])
        if content['feed_end_date'] is not None:
            snapshot['feed_end_date'] = date.fromisoformat(content['feed_end_date'])
        downloaded_at_utc = datetime.fromisoformat(receipt['downloaded_at_utc'])
        offset = downloaded_at_utc.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError(f"The downloaded time is not utc: {receipt_path}")
        snapshot['receipt_id'] = receipt['receipt_id']
        snapshot['downloaded_at_utc'] = downloaded_at_utc
        res.append(snapshot)
    return res


def extract_schedule_zip(archive_root: Path, zip_sha256: str) -> Path:
    content_path = archive_root / zip_sha256
    zip_path = content_path / "original.zip"
    actual_sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if actual_sha256 != zip_sha256:
        raise ValueError(f"Archived ZIP hash does not match {zip_sha256}: {actual_sha256}")
    feed_path = content_path / "feed"
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            destination = feed_path / member.filename
            if not destination.resolve().is_relative_to(feed_path.resolve()):
                raise ValueError(f"ZIP member is outside feed directory: {member.filename!r}")
            if destination.exists():
                continue
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("xb") as target:
                    target.write(source.read())
    return feed_path
