from __future__ import annotations

from datetime import datetime, timezone

from api.interfaces.backtest_request import BacktestRequest
from src.backtest.backtest_data_loader import BacktestDataLoader
from src.backtest.data.backtest_data_set import BacktestDataSet
from src.core.interfaces.data_source import DataSource


class CsvBacktestDataSource(DataSource[BacktestRequest, BacktestDataSet]):
    def __init__(self, path: str):
        self._path = path

    def load(self, request: BacktestRequest) -> BacktestDataSet:
        loader = BacktestDataLoader(self._path)
        data_points = loader.load(request.ticker_symbol)

        if request.start_time is not None:
            start_epoch = int(request.start_time.timestamp())
            data_points = [data_point for data_point in data_points if data_point.timestamp >= start_epoch]
        if request.end_time is not None:
            end_epoch = int(request.end_time.timestamp())
            data_points = [data_point for data_point in data_points if data_point.timestamp <= end_epoch]

        if not data_points:
            raise ValueError(
                f"No historical data for {request.ticker_symbol} in {self._path}"
            )

        return BacktestDataSet(
            dataset_id=self._dataset_id(request.ticker_symbol),
            ticker_symbol=request.ticker_symbol,
            start_time=datetime.fromtimestamp(min(data_point.timestamp for data_point in data_points), tz=timezone.utc),
            end_time=datetime.fromtimestamp(max(data_point.timestamp for data_point in data_points), tz=timezone.utc),
            data_points=tuple(data_points),
        )

    def _dataset_id(self, ticker_symbol: str) -> str:
        return f"csv:{self._path}:{ticker_symbol}"
