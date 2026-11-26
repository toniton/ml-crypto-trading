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

    def test_pinned_market_data_snapshot_survives_live_pruning(self, tmp_path):
        from datetime import datetime, timedelta, timezone
        from decimal import Decimal
        from api.interfaces.backtest_request import BacktestRequest
        from api.interfaces.market_data import MarketData

        def _md(ts: int, price: str) -> MarketData:
            p = Decimal(price)
            return MarketData(
                timestamp=float(ts),
                close_price=p,
                high_price=p,
                low_price=p,
                volume=Decimal("10"),
            )

        store = MarketDataStore(max_age=timedelta(seconds=100))
        store.record("BTC_USD", _md(1000, "100"))
        store.record("BTC_USD", _md(1050, "105"))
        store.record("BTC_USD", _md(1090, "109"))

        service = DatasetService(storage_dir=str(tmp_path))
        resolver = BacktestDataSourceResolver(market_data_store=store, dataset_service=service)

        snapshot_id = resolver.pin_market_data_snapshot(
            ticker_symbol="BTC_USD",
            start_time=datetime.fromtimestamp(1000, tz=timezone.utc),
            end_time=datetime.fromtimestamp(1090, tz=timezone.utc),
        )
        assert snapshot_id is not None

        # Simulate rolling window pruning on the live store
        store.record("BTC_USD", _md(1500, "150"))
        assert [int(o.timestamp) for o in store.observations("BTC_USD")] == [1500]

        pinned_source = resolver.resolve(
            BacktestDataSourceRequest(
                source_type=BacktestDataSourceType.MARKET_DATA,
                source_id=snapshot_id,
            )
        )
        dataset = pinned_source.load(
            BacktestRequest(
                ticker_symbol="BTC_USD",
                data_source=BacktestDataSourceRequest(
                    source_type=BacktestDataSourceType.MARKET_DATA,
                    source_id=snapshot_id,
                ),
            )
        )
        assert list(dataset.timestamps) == [1000, 1050, 1090]

    def test_pinned_snapshot_evicts_oldest_when_over_capacity(self, tmp_path):
        from decimal import Decimal
        from api.interfaces.market_data import MarketData

        store = MarketDataStore(max_age=None)
        store.record(
            "BTC_USD",
            MarketData(
                timestamp=1000.0,
                close_price=Decimal("100"),
                high_price=Decimal("100"),
                low_price=Decimal("100"),
                volume=Decimal("1"),
            ),
        )
        service = DatasetService(storage_dir=str(tmp_path))
        resolver = BacktestDataSourceResolver(
            market_data_store=store,
            dataset_service=service,
            max_snapshots=2,
        )

        snap_1 = resolver.pin_market_data_snapshot("BTC_USD")
        snap_2 = resolver.pin_market_data_snapshot("BTC_USD")
        snap_3 = resolver.pin_market_data_snapshot("BTC_USD")

        assert snap_1 not in resolver._snapshots
        assert snap_2 in resolver._snapshots
        assert snap_3 in resolver._snapshots

