from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from api.interfaces.backtest_request import BacktestRequest
from src.backtest.backtest_data_loader import HistoricalDataPoint
from src.backtest.data.backtest_data_set import BacktestDataSet
from src.core.interfaces.data_source import DataSource
from src.recorder.market_data_store import MarketDataStore


class RecordedMarketDataSource(DataSource[BacktestRequest, BacktestDataSet]):
    def __init__(self, store: MarketDataStore) -> None:
        self._store = store

    def load(self, request: BacktestRequest) -> BacktestDataSet:
        market_data_items = self._store.observations(request.ticker_symbol)

        if request.start_time is not None:
            start_epoch = int(request.start_time.timestamp())
            market_data_items = tuple(
                item for item in market_data_items if int(item.timestamp) >= start_epoch
            )
        if request.end_time is not None:
            end_epoch = int(request.end_time.timestamp())
            market_data_items = tuple(
                item for item in market_data_items if int(item.timestamp) <= end_epoch
            )

        if not market_data_items:
            raise ValueError(
                f"No recorded market data for {request.ticker_symbol}."
            )

        data_points = tuple(
            HistoricalDataPoint(
                timestamp=int(item.timestamp),
                open_price=item.close_price,
                high_price=item.high_price,
                low_price=item.low_price,
                close_price=item.close_price,
                volume=item.volume,
                market_cap=Decimal("0"),
            )
            for item in market_data_items
        )

        return BacktestDataSet(
            dataset_id=(
                    request.data_source.source_id
                    or self._store.dataset_id(request.ticker_symbol)
            ),
            ticker_symbol=request.ticker_symbol,
            start_time=datetime.fromtimestamp(
                min(data_point.timestamp for data_point in data_points), tz=timezone.utc
            ),
            end_time=datetime.fromtimestamp(
                max(data_point.timestamp for data_point in data_points), tz=timezone.utc
            ),
            data_points=data_points,
        )
