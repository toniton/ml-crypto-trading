from datetime import datetime, timezone
from decimal import Decimal

import pytest

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
)
from api.interfaces.market_data import MarketData
from src.backtest.data.recorded_market_data_source import RecordedMarketDataSource
from src.recorder.market_data_store import MarketDataStore


def _market_data(timestamp: int, close: str) -> MarketData:
    return MarketData(
        close_price=Decimal(close),
        high_price=Decimal(close),
        low_price=Decimal(close),
        volume=Decimal("100"),
        timestamp=float(timestamp),
    )


class TestRecordedMarketDataSource:
    def test_loads_frozen_dataset(self):
        store = MarketDataStore()
        store.record("BTC_USD", _market_data(100, "100"))
        store.record("BTC_USD", _market_data(200, "101"))
        source = RecordedMarketDataSource(store)

        dataset = source.load(BacktestRequest(ticker_symbol="BTC_USD"))

        assert dataset.ticker_symbol == "BTC_USD"
        assert dataset.dataset_id == "recorded:BTC_USD"
        assert dataset.timestamps == (100, 200)
        assert [point.close_price for point in dataset.data_points] == [
            Decimal("100"),
            Decimal("101"),
        ]

    def test_filters_by_time_range(self):
        store = MarketDataStore()
        store.record("BTC_USD", _market_data(100, "100"))
        store.record("BTC_USD", _market_data(200, "101"))
        store.record("BTC_USD", _market_data(300, "102"))
        source = RecordedMarketDataSource(store)

        dataset = source.load(BacktestRequest(
            ticker_symbol="BTC_USD",
            start_time=datetime.fromtimestamp(150, tz=timezone.utc),
            end_time=datetime.fromtimestamp(250, tz=timezone.utc),
        ))

        assert dataset.timestamps == (200,)

    def test_uses_source_id_as_dataset_id(self):
        store = MarketDataStore()
        store.record("BTC_USD", _market_data(100, "100"))
        source = RecordedMarketDataSource(store)

        dataset = source.load(BacktestRequest(
            ticker_symbol="BTC_USD",
            data_source=BacktestDataSourceRequest(
                source_type=BacktestDataSourceType.MARKET_DATA,
                source_id="md_abc",
            ),
        ))

        assert dataset.dataset_id == "md_abc"

    def test_empty_raises(self):
        source = RecordedMarketDataSource(MarketDataStore())

        with pytest.raises(ValueError):
            source.load(BacktestRequest(ticker_symbol="BTC_USD"))
