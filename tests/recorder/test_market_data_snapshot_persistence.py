from datetime import timedelta
from decimal import Decimal
import json
import time

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.recorder.market_data_backfill_service import MarketDataBackfillService
from src.recorder.market_data_snapshot_persistence import MarketDataSnapshotPersistence
from src.recorder.market_data_store import MarketDataStore
from unittest.mock import MagicMock


def _market_data(
        timestamp: int,
        close: str,
        bid: str | None = None,
        ask: str | None = None,
) -> MarketData:
    return MarketData(
        close_price=Decimal(close),
        high_price=Decimal(close),
        low_price=Decimal(close),
        volume=Decimal("100"),
        timestamp=float(timestamp),
        bid_price=Decimal(bid) if bid is not None else None,
        ask_price=Decimal(ask) if ask is not None else None,
    )


class TestMarketDataSnapshotPersistence:
    def test_save_and_load_round_trip(self, tmp_path):
        snapshot_path = tmp_path / "snapshot.json"
        writer_store = MarketDataStore(max_age=timedelta(hours=8))
        writer_store.record("BTC_USD", _market_data(1000, "50000.25", bid="50000.00", ask="50000.50"))
        writer_store.record("ETH_USD", _market_data(1010, "3000.10"))

        writer = MarketDataSnapshotPersistence(writer_store, snapshot_path=snapshot_path)
        saved_count = writer.save()

        reader_store = MarketDataStore(max_age=timedelta(hours=8))
        reader = MarketDataSnapshotPersistence(reader_store, snapshot_path=snapshot_path)
        loaded_count = reader.load(now_epoch=1100.0)

        assert saved_count == 2
        assert loaded_count == 2
        btc = reader_store.observations("BTC_USD")[0]
        assert btc.close_price == Decimal("50000.25")
        assert btc.bid_price == Decimal("50000.00")
        assert btc.ask_price == Decimal("50000.50")

    def test_load_filters_expired_observations(self, tmp_path):
        snapshot_path = tmp_path / "snapshot.json"
        writer_store = MarketDataStore(max_age=None)
        writer_store.record("BTC_USD", _market_data(100, "100"))
        writer_store.record("BTC_USD", _market_data(950, "200"))

        MarketDataSnapshotPersistence(writer_store, snapshot_path=snapshot_path).save()

        reader_store = MarketDataStore(max_age=timedelta(seconds=100))
        loaded = MarketDataSnapshotPersistence(reader_store, snapshot_path=snapshot_path).load(now_epoch=1000.0)

        assert loaded == 1
        assert [int(o.timestamp) for o in reader_store.observations("BTC_USD")] == [950]

    def test_load_missing_file_returns_zero(self, tmp_path):
        store = MarketDataStore()
        persistence = MarketDataSnapshotPersistence(store, snapshot_path=tmp_path / "missing.json")

        assert persistence.load() == 0

    def test_load_corrupted_json_returns_zero_without_raising(self, tmp_path):
        snapshot_path = tmp_path / "corrupt.json"
        snapshot_path.write_text("{not valid json", encoding="utf-8")

        store = MarketDataStore()
        persistence = MarketDataSnapshotPersistence(store, snapshot_path=snapshot_path)

        assert persistence.load() == 0

    def test_load_invalid_schema_returns_zero_without_raising(self, tmp_path):
        snapshot_path = tmp_path / "invalid.json"
        snapshot_path.write_text('{"tickers": "not-a-dict"}', encoding="utf-8")

        store = MarketDataStore()
        persistence = MarketDataSnapshotPersistence(store, snapshot_path=snapshot_path)

        assert persistence.load() == 0

    def test_periodic_flush_and_stop_and_flush_writes_snapshot(self, tmp_path):
        snapshot_path = tmp_path / "periodic.json"
        store = MarketDataStore(max_age=None)
        persistence = MarketDataSnapshotPersistence(
            store,
            snapshot_path=snapshot_path,
            flush_interval_seconds=0.05,
        )
        persistence.start_periodic_flush()
        store.record("BTC_USD", _market_data(500, "100"))
        time.sleep(0.1)
        persistence.stop_and_flush()

        restored_store = MarketDataStore(max_age=None)
        restored = MarketDataSnapshotPersistence(restored_store, snapshot_path=snapshot_path).load(now_epoch=600.0)

        assert restored == 1

    def test_flushed_snapshot_is_strictly_ordered_ascending(self, tmp_path):
        snapshot_path = tmp_path / "ordered.json"
        store = MarketDataStore(max_age=None)
        for ts in (300, 100, 500, 200, 400):
            store.record("BTC_USD", _market_data(ts, str(ts)))

        MarketDataSnapshotPersistence(store, snapshot_path=snapshot_path).save()
        raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
        flushed_timestamps = [item["timestamp"] for item in raw["tickers"]["BTC_USD"]]

        assert flushed_timestamps == [100.0, 200.0, 300.0, 400.0, 500.0]

    def test_restored_observations_are_ordered_even_when_file_is_unsorted(self, tmp_path):
        snapshot_path = tmp_path / "unsorted.json"
        payload = {
            "version": 1,
            "saved_at": 1000.0,
            "tickers": {
                "BTC_USD": [
                    {
                        "volume": "10",
                        "high_price": "300",
                        "low_price": "300",
                        "close_price": "300",
                        "timestamp": 300.0,
                        "bid_price": None,
                        "ask_price": None,
                    },
                    {
                        "volume": "10",
                        "high_price": "100",
                        "low_price": "100",
                        "close_price": "100",
                        "timestamp": 100.0,
                        "bid_price": None,
                        "ask_price": None,
                    },
                    {
                        "volume": "10",
                        "high_price": "200",
                        "low_price": "200",
                        "close_price": "200",
                        "timestamp": 200.0,
                        "bid_price": None,
                        "ask_price": None,
                    },
                ]
            },
        }
        snapshot_path.write_text(json.dumps(payload), encoding="utf-8")

        store = MarketDataStore(max_age=None)
        MarketDataSnapshotPersistence(store, snapshot_path=snapshot_path).load(now_epoch=500.0)
        restored_timestamps = [int(o.timestamp) for o in store.observations("BTC_USD")]

        assert restored_timestamps == [100, 200, 300]

    def test_hydrate_backfill_and_reflush_preserves_full_8h_ascending_order(self, tmp_path):
        snapshot_path = tmp_path / "resume_8h.json"
        now = 1_700_030_000.0
        window_start = now - timedelta(hours=8).total_seconds()

        # Simulate a prior run that only persisted the most recent 311 minutes
        initial_store = MarketDataStore(max_age=timedelta(hours=8))
        for minute_offset in range(169, 480):
            ts = int(window_start + minute_offset * 60)
            initial_store.record("BTC_USD", _market_data(ts, "200"))
        MarketDataSnapshotPersistence(initial_store, snapshot_path=snapshot_path).save()

        # Restart: hydrate from disk, then backfill backwards across the full 8h window
        resumed_store = MarketDataStore(max_age=timedelta(hours=8))
        persistence = MarketDataSnapshotPersistence(resumed_store, snapshot_path=snapshot_path)
        persistence.load(now_epoch=now)

        all_candles = [
            Candle(
                open=Decimal("100"),
                low=Decimal("100"),
                high=Decimal("100"),
                close=Decimal("100"),
                start_time=window_start + i * 60,
                volume=Decimal("10"),
            )
            for i in range(481)
        ]

        def _fake_get_candles(exchange, ticker_symbol, timeframe, start_time, end_time, limit):
            del exchange, ticker_symbol, timeframe
            in_range = [c for c in all_candles if start_time <= c.start_time <= end_time]
            return in_range[-limit:]

        rest_manager = MagicMock()
        rest_manager.get_candles.side_effect = _fake_get_candles

        asset = Asset(
            base_ticker_symbol="BTC",
            quote_ticker_symbol="USD",
            quote_decimals=2,
            name="Bitcoin",
            exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
            min_quantity=0.001,
            quantity_decimals=4,
            schedule=AssetSchedule.EVERY_MINUTE,
            candles_timeframe=Timeframe.MIN1,
        )
        report = MarketDataBackfillService(resumed_store, rest_manager).backfill_assets(
            [asset], now_epoch=now
        )

        # Re-flush and inspect both in-memory and on-disk ordering
        persistence.save()
        in_memory_ts = [int(o.timestamp) for o in resumed_store.observations("BTC_USD")]
        flushed_raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
        flushed_ts = [int(item["timestamp"]) for item in flushed_raw["tickers"]["BTC_USD"]]

        assert report.inserted_by_ticker == {"BTC_USD": 170}
        assert in_memory_ts == sorted(set(in_memory_ts))
        assert flushed_ts == in_memory_ts
        assert in_memory_ts[0] == int(window_start)
        assert in_memory_ts[-1] == int(now)
