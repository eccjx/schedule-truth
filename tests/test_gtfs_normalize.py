"""Validate the delegated raw schedule row conversions."""

from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth.gtfs_normalize import (
    normalize_calendar_exception_row,
    normalize_calendar_row,
    normalize_trip_row,
    normalize_stop_time_row,
)
from schedule_truth.gtfs_schedule import scheduled_stop_times_for_date


DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MALFORMED_DATES = (
    "", "2024029", "202402290", "2024-02-29", "2024/02/29",
    "+2024029", "-2024029", " 2024029", "2024029 ", "2024029\n",
    "2024_229", "2024a229", "２０２４０２２９", "٢٠٢٤٠٢٢٩", "2024022²",
)
IMPOSSIBLE_DATES = ("20230229", "19000229", "20240431", "20241301", "20240001", "20240100", "00000101")


def calendar_row():
    row = dict.fromkeys(DAYS, "1")
    row.update(service_id="000123", start_date="20240201", end_date="20240301")
    return row


def exception_row():
    return {"service_id": "000123", "date": "20240229", "exception_type": "1"}


class NormalizeCalendarRowTests(unittest.TestCase):
    def test_valid_conversion_preserves_service_id_and_input(self):
        for flag in ("0", "1"):
            with self.subTest(flag=flag):
                raw = calendar_row()
                for day in DAYS:
                    raw[day] = flag
                original = raw.copy()
                result = normalize_calendar_row(raw)
                expected = dict.fromkeys(DAYS, flag == "1")
                expected.update(service_id="000123", start_date=date(2024, 2, 1), end_date=date(2024, 3, 1))
                self.assertEqual(result, expected)
                self.assertIsInstance(result["service_id"], str)
                for day in DAYS:
                    self.assertIs(type(result[day]), bool)
                self.assertIs(type(result["start_date"]), date)
                self.assertIs(type(result["end_date"]), date)
                self.assertIsNot(result, raw)
                self.assertEqual(raw, original)

    def test_valid_leap_dates_in_both_fields(self):
        for value, expected in (("20240229", date(2024, 2, 29)), ("20000229", date(2000, 2, 29))):
            with self.subTest(value=value):
                raw = calendar_row()
                raw["start_date"] = value
                raw["end_date"] = value
                result = normalize_calendar_row(raw)
                self.assertEqual(result["start_date"], expected)
                self.assertEqual(result["end_date"], expected)

    def test_invalid_dates_include_field_and_value_and_preserve_input(self):
        for field in ("start_date", "end_date"):
            for value in MALFORMED_DATES + IMPOSSIBLE_DATES:
                with self.subTest(field=field, value=value):
                    raw = calendar_row()
                    raw[field] = value
                    original = raw.copy()
                    with self.assertRaises(ValueError) as caught:
                        normalize_calendar_row(raw)
                    self.assertIn(field, str(caught.exception))
                    self.assertIn(repr(value), str(caught.exception))
                    if value in IMPOSSIBLE_DATES:
                        self.assertIsInstance(caught.exception.__cause__, ValueError)
                    self.assertEqual(raw, original)

    def test_invalid_flags_include_field_and_value_and_preserve_input(self):
        for day in DAYS:
            for value in ("", "2", "-1", "01", "true", " 1", "1 ", "１"):
                with self.subTest(day=day, value=value):
                    raw = calendar_row()
                    raw[day] = value
                    original = raw.copy()
                    with self.assertRaises(ValueError) as caught:
                        normalize_calendar_row(raw)
                    self.assertIn(day, str(caught.exception))
                    self.assertIn(repr(value), str(caught.exception))
                    self.assertEqual(raw, original)


class NormalizeCalendarExceptionRowTests(unittest.TestCase):
    def test_both_exception_types_preserve_service_id_and_input(self):
        for kind in ("1", "2"):
            with self.subTest(kind=kind):
                raw = exception_row()
                raw["exception_type"] = kind
                original = raw.copy()
                result = normalize_calendar_exception_row(raw)
                self.assertEqual(result, {"service_id": "000123", "date": date(2024, 2, 29), "exception_type": int(kind)})
                self.assertIsInstance(result["service_id"], str)
                self.assertIs(type(result["date"]), date)
                self.assertIs(type(result["exception_type"]), int)
                self.assertIsNot(result, raw)
                self.assertEqual(raw, original)

    def test_valid_ordinary_and_century_leap_dates(self):
        for value, expected in (("20260921", date(2026, 9, 21)), ("20000229", date(2000, 2, 29))):
            with self.subTest(value=value):
                raw = exception_row()
                raw["date"] = value
                self.assertEqual(normalize_calendar_exception_row(raw)["date"], expected)

    def test_invalid_dates_include_field_and_value_and_preserve_input(self):
        for value in MALFORMED_DATES + IMPOSSIBLE_DATES:
            with self.subTest(value=value):
                raw = exception_row()
                raw["date"] = value
                original = raw.copy()
                with self.assertRaises(ValueError) as caught:
                    normalize_calendar_exception_row(raw)
                self.assertIn("date", str(caught.exception))
                self.assertIn(repr(value), str(caught.exception))
                if value in IMPOSSIBLE_DATES:
                    self.assertIsInstance(caught.exception.__cause__, ValueError)
                self.assertEqual(raw, original)

    def test_invalid_types_include_field_and_value_and_preserve_input(self):
        for value in ("", "0", "3", "-1", "01", "02", "+1", "1.0", "true", " 1", "2 ", "１", "２"):
            with self.subTest(value=value):
                raw = exception_row()
                raw["exception_type"] = value
                original = raw.copy()
                with self.assertRaises(ValueError) as caught:
                    normalize_calendar_exception_row(raw)
                self.assertIn("exception_type", str(caught.exception))
                self.assertIn(repr(value), str(caught.exception))
                self.assertEqual(raw, original)


class NormalizeTripRowTests(unittest.TestCase):
    def test_preserves_identifiers_and_projects_into_new_dictionary(self):
        raw = {"trip_id": "0001", "route_id": "002", "service_id": "000123",
               "trip_headsign": "Downtown"}
        original = raw.copy()
        result = normalize_trip_row(raw)
        self.assertEqual(result, {"trip_id": "0001", "route_id": "002", "service_id": "000123"})
        self.assertIsNot(result, raw)
        self.assertEqual(raw, original)


class NormalizeStopTimeRowTests(unittest.TestCase):
    def test_valid_sequences_preserve_fields_and_input(self):
        for value, expected in (("0", 0), ("2", 2), ("10", 10), ("002", 2)):
            with self.subTest(value=value):
                raw = {"trip_id": "0001", "stop_id": "0002", "stop_sequence": value,
                       "arrival_time": "09:05:07", "departure_time": "09:06:00",
                       "stop_headsign": "Downtown"}
                original = raw.copy()
                result = normalize_stop_time_row(raw)
                self.assertEqual(result, {
                    "trip_id": "0001", "stop_id": "0002", "stop_sequence": expected,
                    "arrival_time": "09:05:07", "departure_time": "09:06:00",
                })
                self.assertIs(type(result["stop_sequence"]), int)
                self.assertIsNot(result, raw)
                self.assertEqual(raw, original)

    def test_preserves_ordinary_extended_and_empty_times(self):
        for arrival, departure in (
            ("9:05:07", "09:06:00"), ("24:00:00", "25:10:00"),
            ("001:02:03", "100:00:00"), ("", ""),
            ("", "00:00:00"), ("00:00:00", ""),
        ):
            with self.subTest(arrival=arrival, departure=departure):
                raw = {"trip_id": "0001", "stop_id": "0002", "stop_sequence": "2",
                       "arrival_time": arrival, "departure_time": departure}
                original = raw.copy()
                result = normalize_stop_time_row(raw)
                self.assertEqual(result["arrival_time"], arrival)
                self.assertEqual(result["departure_time"], departure)
                self.assertEqual(raw, original)

    def test_invalid_sequences_include_context_and_preserve_input(self):
        for value in ("", "-1", "+1", " 1", "1 ", "1\n", "\t1", "1.5", "1_0", "abc", "１２", "١", "²"):
            with self.subTest(value=value):
                raw = {"trip_id": "0001", "stop_id": "0002", "stop_sequence": value,
                       "arrival_time": "09:00:00", "departure_time": "09:01:00"}
                original = raw.copy()
                with self.assertRaises(ValueError) as caught:
                    normalize_stop_time_row(raw)
                self.assertIn("stop_sequence", str(caught.exception))
                self.assertIn(repr(value), str(caught.exception))
                self.assertEqual(raw, original)

    def test_invalid_times_include_context_cause_and_preserve_input(self):
        for field in ("arrival_time", "departure_time"):
            for value in (" ", "09:00", "09:00:00:00", "9:0:00", "09:00:0", "09:60:00",
                          "09:00:60", "-1:00:00", "+1:00:00", "09:00:0.5", "09:00:00 ",
                          "１２:00:00", "09::00", "abc"):
                with self.subTest(field=field, value=value):
                    raw = {"trip_id": "0001", "stop_id": "0002", "stop_sequence": "2",
                           "arrival_time": "09:00:00", "departure_time": "09:01:00"}
                    raw[field] = value
                    original = raw.copy()
                    with self.assertRaises(ValueError) as caught:
                        normalize_stop_time_row(raw)
                    self.assertIn(field, str(caught.exception))
                    self.assertIn(repr(value), str(caught.exception))
                    self.assertIsInstance(caught.exception.__cause__, ValueError)
                    self.assertEqual(raw, original)


class NormalizedScheduleIntegrationTests(unittest.TestCase):
    def test_numeric_stop_order_and_inactive_trip_exclusion(self):
        calendar = normalize_calendar_row({
            "service_id": "001", "monday": "1", "tuesday": "1", "wednesday": "1",
            "thursday": "1", "friday": "1", "saturday": "0", "sunday": "0",
            "start_date": "20260921", "end_date": "20260927",
        })
        exception = normalize_calendar_exception_row({
            "service_id": "002", "date": "20260921", "exception_type": "2",
        })
        active_trip = normalize_trip_row({"trip_id": "0001", "route_id": "01", "service_id": "001"})
        inactive_trip = normalize_trip_row({"trip_id": "0002", "route_id": "01", "service_id": "002"})
        stop_10 = normalize_stop_time_row({
            "trip_id": "0001", "stop_id": "010", "stop_sequence": "10",
            "arrival_time": "25:10:00", "departure_time": "25:11:00",
        })
        stop_2 = normalize_stop_time_row({
            "trip_id": "0001", "stop_id": "002", "stop_sequence": "2",
            "arrival_time": "24:00:00", "departure_time": "",
        })
        inactive_stop = normalize_stop_time_row({
            "trip_id": "0002", "stop_id": "003", "stop_sequence": "1",
            "arrival_time": "09:00:00", "departure_time": "09:01:00",
        })
        result = scheduled_stop_times_for_date(
            date(2026, 9, 21), [calendar], [exception],
            [active_trip, inactive_trip], [stop_10, inactive_stop, stop_2],
        )
        self.assertEqual(result, {"0001": [stop_2, stop_10]})
        self.assertEqual(result["0001"][0]["stop_sequence"], 2)
        self.assertEqual(result["0001"][1]["stop_sequence"], 10)
        self.assertNotIn("0002", result)


if __name__ == "__main__":
    unittest.main()
