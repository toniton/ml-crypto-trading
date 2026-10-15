from datetime import timedelta

import pytest

from src.retention.durations import RetentionDuration, format_duration, parse_duration


class TestParseDuration:
    def test_returns_none_for_keep(self):
        assert RetentionDuration.parse("KEEP") is None
        assert RetentionDuration.parse("keep") is None
        assert parse_duration("KEEP") is None

    def test_parses_supported_units(self):
        assert RetentionDuration.parse("90d") == timedelta(days=90)
        assert RetentionDuration.parse("12h") == timedelta(hours=12)
        assert RetentionDuration.parse("30m") == timedelta(minutes=30)
        assert RetentionDuration.parse("45s") == timedelta(seconds=45)

    def test_passthrough_types(self):
        assert RetentionDuration.parse(timedelta(days=1)) == timedelta(days=1)
        assert RetentionDuration.parse(60) == timedelta(seconds=60)

    @pytest.mark.parametrize("value", ["", "abc", "90", "d90", "1y", "-1d"])
    def test_rejects_invalid(self, value):
        with pytest.raises(ValueError):
            RetentionDuration.parse(value)


class TestFormatDuration:
    def test_formats_units(self):
        assert RetentionDuration.format(None) == "KEEP"
        assert RetentionDuration.format(timedelta(days=90)) == "90d"
        assert RetentionDuration.format(timedelta(hours=5)) == "5h"
        assert RetentionDuration.format(timedelta(minutes=5)) == "5m"
        assert RetentionDuration.format(timedelta(seconds=5)) == "5s"
        assert format_duration(None) == "KEEP"
