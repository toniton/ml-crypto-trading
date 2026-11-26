from __future__ import annotations

import uuid
from collections import OrderedDict
from datetime import datetime
from threading import Lock
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
from src.server.services.dataset_service import DatasetService

MAX_PINNED_SNAPSHOTS = 64


class BacktestDataSourceResolver:
    def __init__(
            self,
            market_data_store: MarketDataStore,
            dataset_service: DatasetService,
            max_snapshots: int = MAX_PINNED_SNAPSHOTS,
    ) -> None:
        self._market_data_store = market_data_store
        self._dataset_service = dataset_service
        self._max_snapshots = max(1, max_snapshots)
        self._snapshots: OrderedDict[str, MarketDataStore] = OrderedDict()
        self._snapshot_lock = Lock()

    def pin_market_data_snapshot(
            self,
            ticker_symbol: str,
            start_time: Optional[datetime] = None,
            end_time: Optional[datetime] = None,
    ) -> Optional[str]:
        """Freeze current recorded market data so queued candidates share an identical window."""
        start_epoch = int(start_time.timestamp()) if start_time is not None else None
        end_epoch = int(end_time.timestamp()) if end_time is not None else None
        frozen_store = self._market_data_store.snapshot(
            ticker_symbol,
            start_epoch=start_epoch,
            end_epoch=end_epoch,
        )
        if frozen_store.size(ticker_symbol) == 0:
            return None

        snapshot_id = f"snapshot:{uuid.uuid4().hex[:12]}"
        with self._snapshot_lock:
            self._snapshots[snapshot_id] = frozen_store
            while len(self._snapshots) > self._max_snapshots:
                self._snapshots.popitem(last=False)
        return snapshot_id

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
            if request.source_id:
                with self._snapshot_lock:
                    pinned_store = self._snapshots.get(request.source_id)
                if pinned_store is not None:
                    return RecordedMarketDataSource(pinned_store)
            return RecordedMarketDataSource(self._market_data_store)

        raise ValueError(f"Unsupported data source type: {request.source_type}")


# Alias for shared simulation components (Backtest, Walk-Forward, Optimization)
SimulationDataSourceResolver = BacktestDataSourceResolver
