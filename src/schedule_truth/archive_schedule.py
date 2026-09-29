from datetime import datetime, date
from pathlib import Path
import hashlib
from uuid import uuid4
import json
import csv
import io
import zipfile

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
        except (KeyError, IndexError, ValueError) as error:
            feed_start_date = None
            feed_end_date = None
            coverage_error = f"missing or invalid coverage: {error}"
        with archive.open("agency.txt") as member:
             text = io.TextIOWrapper(member, encoding="utf-8-sig")
             feed_info_rows = list(csv.DictReader(text))
             timezone = feed_info_rows[0]['agency_timezone']

        
    content = {
            "zip_sha256": zip_sha256,
            "zip_path": destination_path,
            "feed_start_date": feed_start_date,
            "feed_end_date": feed_end_date,
            "agency_timezone": timezone,
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
