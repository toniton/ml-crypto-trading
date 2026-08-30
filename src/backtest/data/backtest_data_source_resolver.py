from __future__ import annotations

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
)
from src.backtest.data.backtest_data_set import BacktestDataSet
from src.backtest.data.csv_backtest_data_source import CsvBacktestDataSource
from src.core.interfaces.data_source import DataSource


class BacktestDataSourceResolver:
    def resolve(
            self,
            request: BacktestDataSourceRequest,
    ) -> DataSource[BacktestRequest, BacktestDataSet]:
        if request.source_type == BacktestDataSourceType.CSV:
            if not request.path:
                raise ValueError("A CSV data source requires a 'path'.")
            return CsvBacktestDataSource(request.path)

        if request.source_type == BacktestDataSourceType.MARKET_DATA:
            raise NotImplementedError(
                "Recorded market-data sources are not implemented yet; "
                "use a CSV source."
            )

        raise ValueError(f"Unsupported data source type: {request.source_type}")
