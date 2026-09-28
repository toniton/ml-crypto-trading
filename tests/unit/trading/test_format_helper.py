import unittest
from datetime import datetime, timezone
from decimal import Decimal

from src.trading.helpers.format_helper import FormatHelper


class TestFormatHelper(unittest.TestCase):
    def test_format_decimal_with_none(self):
        self.assertEqual(FormatHelper.format_decimal(None), "None")

    def test_format_decimal_with_scientific_notation(self):
        self.assertEqual(FormatHelper.format_decimal(Decimal("7.8E-7")), "0.00000078")

    def test_format_decimal_with_trailing_zeros(self):
        self.assertEqual(FormatHelper.format_decimal(Decimal("0.000000")), "0")
        self.assertEqual(FormatHelper.format_decimal(Decimal("1.5000")), "1.5")
        self.assertEqual(FormatHelper.format_decimal(Decimal("100.0")), "100")

    def test_format_decimal_with_infinities(self):
        self.assertEqual(FormatHelper.format_decimal(Decimal("inf")), "Infinity")
        self.assertEqual(FormatHelper.format_decimal(Decimal("-inf")), "-Infinity")

    def test_format_decimal_with_floats_and_ints(self):
        self.assertEqual(FormatHelper.format_decimal(100), "100")
        self.assertEqual(FormatHelper.format_decimal(12.34), "12.34")

    def test_format_decimal_with_invalid_string(self):
        self.assertEqual(FormatHelper.format_decimal("not_a_number"), "not_a_number")

    def test_parse_iso_datetime_with_utc_z(self):
        result = FormatHelper.parse_iso_datetime("2026-09-28T01:50:00Z")
        expected = datetime(2026, 9, 28, 1, 50, 0, tzinfo=timezone.utc)
        self.assertEqual(result, expected)

    def test_parse_iso_datetime_with_offset(self):
        result = FormatHelper.parse_iso_datetime("2026-09-28T03:50:00+02:00")
        expected = datetime(2026, 9, 28, 1, 50, 0, tzinfo=timezone.utc)
        self.assertEqual(result, expected)

    def test_parse_iso_datetime_naive(self):
        result = FormatHelper.parse_iso_datetime("2026-09-28T01:50:00")
        expected = datetime(2026, 9, 28, 1, 50, 0, tzinfo=timezone.utc)
        self.assertEqual(result, expected)

    def test_parse_iso_datetime_invalid_string(self):
        result = FormatHelper.parse_iso_datetime("invalid-timestamp")
        expected = datetime.min.replace(tzinfo=timezone.utc)
        self.assertEqual(result, expected)
