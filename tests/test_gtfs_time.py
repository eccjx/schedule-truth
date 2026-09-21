"""Regression checks for the parser's existing string-input behavior."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from schedule_truth.gtfs_time import parse_gtfs_time


class ParseGtfsTimeTests(unittest.TestCase):
    def test_valid_times_return_integer_seconds_without_wrapping(self):
        for value, expected in [
            ("00:00:00", 0), ("00:00:01", 1), ("00:01:00", 60),
            ("01:00:00", 3600), ("9:05:07", 32707),
            ("12:34:56", 45296), ("23:59:59", 86399),
            ("24:00:00", 86400), ("25:10:00", 90600),
        ]:
            with self.subTest(value=value):
                result = parse_gtfs_time(value)
                self.assertIsInstance(result, int)
                self.assertEqual(result, expected)

    def test_rejects_missing_or_extra_components(self):
        for value in ["", "12", "12:34", "12:34:56:00", ":00:00", "12::00", "12:00:"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_gtfs_time(value)

    def test_rejects_invalid_minute_and_second_widths_or_ranges(self):
        for value in ["12:1:00", "12:00:1", "12:001:00", "12:00:001",
                      "12:60:00", "12:00:60", "12:99:99"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_gtfs_time(value)

    def test_rejects_non_ascii_digits_signs_whitespace_and_fractions(self):
        for value in ["-1:00:00", "+1:00:00", "12:-1:00", "12:00:+1",
                      "ab:00:00", "12:ab:00", "12:00:ab", "12:00:0.5",
                      " 12:00:00", "12:00:00 ", "12:00:00\n", "12:\t0:00",
                      "１２:00:00", "12:٠١:00", "12:00:０１"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_gtfs_time(value)


if __name__ == "__main__":
    unittest.main()
