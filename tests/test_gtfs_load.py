"""Exercise real CSV decoding and normalizers through temporary files."""

from datetime import date
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth.gtfs_load import (
    load_calendar_rows, load_calendar_exception_rows, load_trip_rows,
    load_stop_time_rows,
)
from gtfs_fixture import TABLES, write_table


LOADERS = {
    "calendar.txt": load_calendar_rows,
    "calendar_dates.txt": load_calendar_exception_rows,
    "trips.txt": load_trip_rows,
    "stop_times.txt": load_stop_time_rows,
}


class LoadGtfsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_all_loaders_decode_utf8_with_and_without_bom_and_normalize(self):
        expected_calendar = {
            "service_id": "001", "monday": True, "tuesday": True,
            "wednesday": True, "thursday": True, "friday": True,
            "saturday": False, "sunday": False,
            "start_date": date(2026, 9, 21), "end_date": date(2026, 9, 27),
        }
        for encoding in ("utf-8", "utf-8-sig"):
            with self.subTest(encoding=encoding):
                calendar = load_calendar_rows(write_table(self.folder, "calendar.txt", encoding=encoding))
                self.assertEqual(calendar, [expected_calendar])
                self.assertIs(type(calendar[0]["tuesday"]), bool)
                self.assertEqual(load_calendar_exception_rows(write_table(
                    self.folder, "calendar_dates.txt",
                    [["001", "20260922", "2"], ["002", "20260922", "1"]], encoding,
                )), [
                    {"service_id": "001", "date": date(2026, 9, 22), "exception_type": 2},
                    {"service_id": "002", "date": date(2026, 9, 22), "exception_type": 1},
                ])
                self.assertEqual(load_trip_rows(write_table(self.folder, "trips.txt", encoding=encoding)), [
                    {"trip_id": "78942566", "route_id": "01", "service_id": "001"},
                    {"trip_id": "INACTIVE", "route_id": "01", "service_id": "002"},
                ])
                self.assertEqual(load_stop_time_rows(write_table(self.folder, "stop_times.txt", encoding=encoding)), [
                    {"trip_id": "78942566", "stop_id": "LAST", "stop_sequence": 10,
                     "arrival_time": "25:10:00", "departure_time": "25:11:00"},
                    {"trip_id": "INACTIVE", "stop_id": "OTHER", "stop_sequence": 1,
                     "arrival_time": "09:00:00", "departure_time": "09:01:00"},
                    {"trip_id": "78942566", "stop_id": "FIRST", "stop_sequence": 2,
                     "arrival_time": "23:59:00", "departure_time": "24:00:00"},
                ])

    def test_csv_quoting_unicode_and_embedded_newlines(self):
        identifier = '00,café "中央"\nline'
        path = write_table(self.folder, "trips.txt", [[identifier, "01", "001"]])
        self.assertEqual(load_trip_rows(path), [{"trip_id": identifier, "route_id": "01", "service_id": "001"}])

    def test_blank_stop_times_are_preserved(self):
        path = write_table(self.folder, "stop_times.txt", [["0001", "0002", "002", "", ""]])
        self.assertEqual(load_stop_time_rows(path), [{"trip_id": "0001", "stop_id": "0002",
            "stop_sequence": 2, "arrival_time": "", "departure_time": ""}])

    def test_header_only_tables_return_empty_lists(self):
        for name, loader in LOADERS.items():
            with self.subTest(name=name):
                self.assertEqual(loader(write_table(self.folder, name, [])), [])

    def test_missing_files_raise_file_not_found(self):
        for name, loader in LOADERS.items():
            with self.subTest(name=name):
                with self.assertRaises(FileNotFoundError):
                    loader(self.folder / name)

    def test_normalization_failures_are_not_silently_skipped(self):
        cases = [
            ("calendar.txt", "start_date", "20260230"),
            ("calendar.txt", "tuesday", "2"),
            ("calendar_dates.txt", "exception_type", "3"),
            ("calendar_dates.txt", "date", "20260230"),
            ("stop_times.txt", "stop_sequence", "two"),
            ("stop_times.txt", "arrival_time", "25:60:00"),
            ("stop_times.txt", "departure_time", "invalid"),
        ]
        for name, field, value in cases:
            with self.subTest(name=name, field=field):
                headers, defaults = TABLES[name]
                valid = list(defaults[0] if defaults else ["001", "20260922", "1"])
                invalid = valid.copy()
                invalid[headers.index(field)] = value
                path = write_table(self.folder, name, [valid, invalid])
                original = path.read_bytes()
                with self.assertRaises(ValueError) as caught:
                    LOADERS[name](path)
                self.assertIn(field, str(caught.exception))
                self.assertEqual(path.read_bytes(), original)

    def test_repeated_loads_preserve_source_and_do_not_share_results(self):
        for name, loader in LOADERS.items():
            with self.subTest(name=name):
                rows = [["001", "20260922", "1"]] if name == "calendar_dates.txt" else None
                path = write_table(self.folder, name, rows)
                original = path.read_bytes()
                first = loader(path)
                second = loader(path)
                self.assertEqual(first, second)
                first[0].clear()
                self.assertEqual(loader(path), second)
                self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
