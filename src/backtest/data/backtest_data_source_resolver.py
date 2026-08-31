from __future__ import annotations

from typing import Optional

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


class BacktestDataSourceResolver:
    def __init__(self, market_data_store: Optional[MarketDataStore] = None) -> None:
        self._market_data_store = market_data_store

    def resolve(
            self,
            request: BacktestDataSourceRequest,
    ) -> DataSource[BacktestRequest, BacktestDataSet]:
        if request.source_type == BacktestDataSourceType.CSV:
            if not request.path:
                raise ValueError("A CSV data source requires a 'path'.")
            return CsvBacktestDataSource(request.path)

        if request.source_type == BacktestDataSourceType.MARKET_DATA:
            if self._market_data_store is None:
                raise ValueError(
                    "A recorded market-data source requires a MarketDataStore."
                )
            return RecordedMarketDataSource(self._market_data_store)

        raise ValueError(f"Unsupported data source type: {request.source_type}")
