import pytest

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
)
from src.backtest.data.backtest_data_source_resolver import BacktestDataSourceResolver
from src.backtest.data.csv_backtest_data_source import CsvBacktestDataSource
from src.backtest.data.recorded_market_data_source import RecordedMarketDataSource
from src.recorder.market_data_store import MarketDataStore


class TestBacktestDataSourceResolver:
    def test_resolves_csv(self):
        resolver = BacktestDataSourceResolver()

        source = resolver.resolve(
            BacktestDataSourceRequest(
                source_type=BacktestDataSourceType.CSV, path="/data"
            )
        )

        assert isinstance(source, CsvBacktestDataSource)

    def test_resolves_market_data(self):
        store = MarketDataStore()
        resolver = BacktestDataSourceResolver(market_data_store=store)

        source = resolver.resolve(
            BacktestDataSourceRequest(source_type=BacktestDataSourceType.MARKET_DATA)
        )

        assert isinstance(source, RecordedMarketDataSource)

    def test_market_data_requires_store(self):
        resolver = BacktestDataSourceResolver()

        with pytest.raises(ValueError):
            resolver.resolve(
                BacktestDataSourceRequest(source_type=BacktestDataSourceType.MARKET_DATA)
            )
