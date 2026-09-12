import pytest

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
)
from src.backtest.data.backtest_data_source_resolver import BacktestDataSourceResolver
from src.backtest.data.csv_backtest_data_source import CsvBacktestDataSource
from src.backtest.data.recorded_market_data_source import RecordedMarketDataSource
from src.recorder.market_data_store import MarketDataStore
from src.server.services.dataset_service import DatasetService


class TestBacktestDataSourceResolver:
    def test_resolves_csv_with_path(self, tmp_path):
        store = MarketDataStore()
        service = DatasetService(storage_dir=str(tmp_path))
        resolver = BacktestDataSourceResolver(market_data_store=store, dataset_service=service)

        source = resolver.resolve(
            BacktestDataSourceRequest(
                source_type=BacktestDataSourceType.CSV, path="/data"
            )
        )

        assert isinstance(source, CsvBacktestDataSource)

    def test_resolves_csv_with_source_id(self, tmp_path):
        store = MarketDataStore()
        service = DatasetService(storage_dir=str(tmp_path))
        csv_file = tmp_path / "dataset_123.csv"
        csv_file.write_text("timestamp;open;high;low;close;volume\n")

        resolver = BacktestDataSourceResolver(market_data_store=store, dataset_service=service)

        source = resolver.resolve(
            BacktestDataSourceRequest(
                source_type=BacktestDataSourceType.CSV, source_id="dataset_123"
            )
        )

        assert isinstance(source, CsvBacktestDataSource)

    def test_csv_without_valid_path_or_source_id_raises(self, tmp_path):
        store = MarketDataStore()
        service = DatasetService(storage_dir=str(tmp_path))
        resolver = BacktestDataSourceResolver(market_data_store=store, dataset_service=service)

        with pytest.raises(ValueError, match="requires a valid 'path' or 'source_id'"):
            resolver.resolve(
                BacktestDataSourceRequest(source_type=BacktestDataSourceType.CSV)
            )

    def test_resolves_market_data(self, tmp_path):
        store = MarketDataStore()
        service = DatasetService(storage_dir=str(tmp_path))
        resolver = BacktestDataSourceResolver(market_data_store=store, dataset_service=service)

        source = resolver.resolve(
            BacktestDataSourceRequest(source_type=BacktestDataSourceType.MARKET_DATA)
        )

        assert isinstance(source, RecordedMarketDataSource)

