from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.recorder.market_data_backfill_service import (
    DEFAULT_BACKFILL_MAX_RECORDS,
    MarketDataBackfillService,
    backfill_policy_for,
)
from src.recorder.market_data_store import MarketDataStore


def _asset(
        base: str = "BTC",
        timeframe: Timeframe = Timeframe.MIN5,
        enabled: bool = True,
) -> Asset:
    return Asset(
        base_ticker_symbol=base,
        quote_ticker_symbol="USD",
        quote_decimals=2,
        name=base,
        exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
        min_quantity=0.001,
        quantity_decimals=4,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=timeframe,
        enabled=enabled,
    )


def _candle(start_time: float, close: str) -> Candle:
    return Candle(
        open=Decimal(close),
        low=Decimal(close),
        high=Decimal(close),
        close=Decimal(close),
        start_time=start_time,
        volume=Decimal("10"),
    )


class TestMarketDataBackfillService:
    def test_cold_start_backfills_full_max_age_window_with_asset_timeframe(self):
        store = MarketDataStore(max_age=timedelta(hours=8))
        rest_manager = MagicMock()
        now = 1_700_030_000.0
        rest_manager.get_candles.return_value = [
            _candle(now - 600, "100"),
            _candle(now - 300, "101"),
        ]

        service = MarketDataBackfillService(store, rest_manager)
        report = service.backfill_assets([_asset(timeframe=Timeframe.MIN5)], now_epoch=now)

        rest_manager.get_candles.assert_called_once_with(
            exchange="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            timeframe=Timeframe.MIN5,
            start_time=now - timedelta(hours=8).total_seconds(),
            end_time=now,
            limit=300,
        )
        assert report.inserted_by_ticker == {"BTC_USD": 2}

    def test_resumes_from_latest_persisted_timestamp_without_overwriting(self):
        store = MarketDataStore(max_age=timedelta(hours=8))
        now = 1_700_030_000.0
        window_start = int(now - timedelta(hours=8).total_seconds())
        persisted_ts = int(now - 600)
        store.record(
            "BTC_USD",
            MarketData(
                close_price=Decimal("888"),
                high_price=Decimal("888"),
                low_price=Decimal("888"),
                volume=Decimal("5"),
                timestamp=float(window_start),
            ),
        )
        store.record(
            "BTC_USD",
            MarketData(
                close_price=Decimal("999"),
                high_price=Decimal("999"),
                low_price=Decimal("999"),
                volume=Decimal("5"),
                timestamp=float(persisted_ts),
                bid_price=Decimal("998"),
                ask_price=Decimal("1000"),
            ),
        )
        rest_manager = MagicMock()
        rest_manager.get_candles.return_value = [
            _candle(float(persisted_ts), "100"),
            _candle(float(persisted_ts + 300), "101"),
        ]

        service = MarketDataBackfillService(store, rest_manager)
        report = service.backfill_assets([_asset(timeframe=Timeframe.MIN5)], now_epoch=now)

        assert rest_manager.get_candles.call_count == 1
        assert rest_manager.get_candles.call_args.kwargs["start_time"] == float(persisted_ts)
        assert report.inserted_by_ticker == {"BTC_USD": 1}
        observations = store.observations("BTC_USD")
        assert observations[1].close_price == Decimal("999")
        assert observations[2].close_price == Decimal("101")

    def test_backfills_both_recent_gap_and_older_tail_when_snapshot_is_partial(self):
        store = MarketDataStore(max_age=timedelta(hours=8))
        now = 1_700_030_000.0
        window_start = now - timedelta(hours=8).total_seconds()
        # Hydrated snapshot only covers the last 3 hours minus 5 minutes of downtime
        hydrated_start = now - timedelta(hours=3).total_seconds()
        hydrated_end = now - 300.0
        store.record(
            "BTC_USD",
            MarketData(
                close_price=Decimal("500"),
                high_price=Decimal("500"),
                low_price=Decimal("500"),
                volume=Decimal("1"),
                timestamp=hydrated_start,
            ),
        )
        store.record(
            "BTC_USD",
            MarketData(
                close_price=Decimal("501"),
                high_price=Decimal("501"),
                low_price=Decimal("501"),
                volume=Decimal("1"),
                timestamp=hydrated_end,
            ),
        )

        all_candles = [_candle(window_start + i * 300, "100") for i in range(97)]

        def _fake_get_candles(
                exchange, ticker_symbol, timeframe, start_time, end_time, limit
        ):
            del exchange, ticker_symbol, timeframe
            in_range = [c for c in all_candles if start_time <= c.start_time <= end_time]
            return in_range[-limit:]

        rest_manager = MagicMock()
        rest_manager.get_candles.side_effect = _fake_get_candles

        service = MarketDataBackfillService(store, rest_manager)
        report = service.backfill_assets([_asset(timeframe=Timeframe.MIN5)], now_epoch=now)

        # First call fills recent downtime gap [hydrated_end, now], second fills older tail [window_start, hydrated_start - 300]
        assert rest_manager.get_candles.call_count == 2
        first_kwargs = rest_manager.get_candles.call_args_list[0].kwargs
        second_kwargs = rest_manager.get_candles.call_args_list[1].kwargs
        assert first_kwargs["start_time"] == hydrated_end
        assert first_kwargs["end_time"] == now
        assert second_kwargs["start_time"] == window_start
        assert second_kwargs["end_time"] == hydrated_start - 300.0
        assert store.earliest_timestamp("BTC_USD") == int(window_start)
        assert store.latest_timestamp("BTC_USD") == int(now)
        assert report.inserted_by_ticker["BTC_USD"] > 1

    def test_paginates_backwards_from_most_recent(self):
        store = MarketDataStore(max_age=timedelta(minutes=3))
        now = 1_700_010_000.0
        start = now - 180
        rest_manager = MagicMock()
        rest_manager.get_candles.side_effect = [
            [_candle(start + 120, "102"), _candle(now, "103")],
            [_candle(start, "100"), _candle(start + 60, "101")],
        ]

        service = MarketDataBackfillService(store, rest_manager, page_size=2, max_pages=5)
        report = service.backfill_assets([_asset(timeframe=Timeframe.MIN1)], now_epoch=now)

        assert rest_manager.get_candles.call_count == 2
        first_call = rest_manager.get_candles.call_args_list[0].kwargs
        second_call = rest_manager.get_candles.call_args_list[1].kwargs
        assert first_call["end_time"] == now
        assert second_call["end_time"] < first_call["end_time"]
        assert report.inserted_by_ticker == {"BTC_USD": 4}

    def test_caps_backfill_at_max_records_keeping_most_recent(self):
        store = MarketDataStore(max_age=timedelta(hours=8))
        now = 1_700_030_000.0
        start = now - timedelta(hours=8).total_seconds()
        all_candles = [_candle(start + i * 60, str(i)) for i in range(480)]

        def _fake_get_candles(
                exchange, ticker_symbol, timeframe, start_time, end_time, limit
        ):
            del exchange, ticker_symbol, timeframe
            in_range = [c for c in all_candles if start_time <= c.start_time <= end_time]
            return in_range[-limit:]

        rest_manager = MagicMock()
        rest_manager.get_candles.side_effect = _fake_get_candles

        service = MarketDataBackfillService(store, rest_manager, page_size=3, max_records=5)
        report = service.backfill_assets([_asset(timeframe=Timeframe.MIN1)], now_epoch=now)

        assert DEFAULT_BACKFILL_MAX_RECORDS == 10_000
        assert report.inserted_by_ticker == {"BTC_USD": 5}
        closes = [o.close_price for o in store.observations("BTC_USD")]
        assert closes == [Decimal("475"), Decimal("476"), Decimal("477"), Decimal("478"), Decimal("479")]

    def test_chunks_time_window_for_end_ts_anchored_exchanges(self):
        store = MarketDataStore(max_age=timedelta(hours=8))
        now = 1_700_030_000.0
        start = now - timedelta(hours=8).total_seconds()
        all_candles = [_candle(start + i * 60, "100") for i in range(480)]

        def _fake_cryptodotcom_get_candles(
                exchange, ticker_symbol, timeframe, start_time, end_time, limit
        ):
            del exchange, ticker_symbol, timeframe
            in_range = [c for c in all_candles if start_time <= c.start_time <= end_time]
            return in_range[-limit:]

        rest_manager = MagicMock()
        rest_manager.get_candles.side_effect = _fake_cryptodotcom_get_candles

        service = MarketDataBackfillService(store, rest_manager, page_size=300, max_pages=10)
        report = service.backfill_assets([_asset(timeframe=Timeframe.MIN1)], now_epoch=now)

        assert rest_manager.get_candles.call_count == 2
        assert report.inserted_by_ticker == {"BTC_USD": 480}

    def test_failure_for_one_asset_does_not_abort_other_assets(self):
        store = MarketDataStore(max_age=timedelta(hours=8))
        now = 1_700_030_000.0
        rest_manager = MagicMock()
        rest_manager.get_candles.side_effect = [
            RuntimeError("exchange timeout"),
            [_candle(now - 300, "2500")],
        ]

        service = MarketDataBackfillService(store, rest_manager)
        report = service.backfill_assets([_asset(base="BTC"), _asset(base="ETH")], now_epoch=now)

        assert "BTC_USD" in report.failed_tickers
        assert report.inserted_by_ticker == {"ETH_USD": 1}

    def test_skips_disabled_assets(self):
        store = MarketDataStore(max_age=timedelta(hours=8))
        rest_manager = MagicMock()

        service = MarketDataBackfillService(store, rest_manager)
        report = service.backfill_assets([_asset(base="BTC", enabled=False)], now_epoch=1_700_030_000.0)

        rest_manager.get_candles.assert_not_called()
        assert report.skipped_tickers == ["BTC_USD"]

    def test_configure_store_retention_extends_max_age_by_timeframe(self):
        store = MarketDataStore()
        assets = [
            _asset(base="BTC", timeframe=Timeframe.MIN1),
            _asset(base="ETH", timeframe=Timeframe.MIN5),
            _asset(base="SOL", timeframe=Timeframe.HOUR1),
        ]

        MarketDataBackfillService.configure_store_retention(store, assets)

        assert store.max_age_for("BTC_USD") == timedelta(hours=12)
        assert store.max_age_for("ETH_USD") == timedelta(days=3)
        assert store.max_age_for("SOL_USD") == timedelta(days=30)
        assert backfill_policy_for(Timeframe.MIN1).max_records == 1_000
        assert backfill_policy_for(Timeframe.DAY7).max_records == 500
