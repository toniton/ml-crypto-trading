from __future__ import annotations

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
)
from src.backtest.data.backtest_data_set import BacktestDataSet
from src.backtest.data.csv_backtest_data_source import CsvBacktestDataSource
from src.backtest.data.recorded_market_data_source import RecordedMarketDataSource
from src.core.interfaces.data_source import DataSource
from src.recorder.market_data_store import MarketDataStore
from src.server.services.dataset_service import DatasetService


class BacktestDataSourceResolver:
    def __init__(
            self,
            market_data_store: MarketDataStore,
            dataset_service: DatasetService,
    ) -> None:
        self._market_data_store = market_data_store
        self._dataset_service = dataset_service

    def resolve(
            self,
            request: BacktestDataSourceRequest,
    ) -> DataSource[BacktestRequest, BacktestDataSet]:
        if request.source_type == BacktestDataSourceType.CSV:
            path = request.path
            if not path and request.source_id:
                path = self._dataset_service.get_dataset_csv_path(request.source_id)
            if not path:
                raise ValueError("A CSV data source requires a valid 'path' or 'source_id'.")
            return CsvBacktestDataSource(path)

        if request.source_type == BacktestDataSourceType.MARKET_DATA:
            return RecordedMarketDataSource(self._market_data_store)

        raise ValueError(f"Unsupported data source type: {request.source_type}")

