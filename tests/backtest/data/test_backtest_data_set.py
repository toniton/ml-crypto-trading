from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.backtest.backtest_data_loader import HistoricalDataPoint
from src.backtest.data.backtest_data_set import BacktestDataSet


def _point(timestamp: int, close: str) -> HistoricalDataPoint:
    return HistoricalDataPoint(
        timestamp=timestamp,
        open_price=Decimal(close),
        high_price=Decimal(close),
        low_price=Decimal(close),
        close_price=Decimal(close),
        volume=Decimal("1000"),
        market_cap=Decimal("0"),
    )


def _dataset(data_points: list[HistoricalDataPoint]) -> BacktestDataSet:
    timestamps = [data_point.timestamp for data_point in data_points]
    return BacktestDataSet(
        dataset_id="csv:/data/BTC_USD",
        ticker_symbol="BTC_USD",
        start_time=datetime.fromtimestamp(min(timestamps), tz=timezone.utc),
        end_time=datetime.fromtimestamp(max(timestamps), tz=timezone.utc),
        data_points=tuple(data_points),
    )


class TestBacktestDataSet:
    def test_points_are_immutable(self):
        ds = _dataset([_point(100, "100"), _point(200, "101")])

        assert isinstance(ds.data_points, tuple)
        with pytest.raises(AttributeError):
            ds.data_points[0].close_price = Decimal("999")  # type: ignore[misc]

    def test_dataset_is_frozen(self):
        ds = _dataset([_point(100, "100")])

        with pytest.raises(AttributeError):
            ds.ticker_symbol = "ETH_USD"  # type: ignore[misc]

    def test_rejects_unsorted_timestamps(self):
        with pytest.raises(ValueError):
            _dataset([_point(200, "101"), _point(100, "100")])

    def test_rejects_duplicate_timestamps(self):
        with pytest.raises(ValueError):
            _dataset([_point(100, "100"), _point(100, "101")])

    def test_get_is_exact_no_interpolation(self):
        ds = _dataset([_point(100, "100"), _point(200, "101")])

        assert ds.get(100).close_price == Decimal("100")
        assert ds.get(200).close_price == Decimal("101")
        assert ds.get(150) is None

    def test_timestamps_are_ordered(self):
        ds = _dataset([_point(100, "100"), _point(200, "101"), _point(300, "102")])

        assert ds.timestamps == (100, 200, 300)
        assert len(ds) == 3
