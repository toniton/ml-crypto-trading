from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Iterable, Optional

from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from src.exchange.interfaces.exchange_rest_manager import ExchangeRestManager
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.recorder.market_data_store import DEFAULT_MAX_AGE, MarketDataStore

DEFAULT_BACKFILL_PAGE_SIZE = 300
DEFAULT_BACKFILL_MAX_RECORDS = 10_000
DEFAULT_BACKFILL_MAX_PAGES = 50


@dataclass(frozen=True)
class TimeframeBackfillPolicy:
    max_age: timedelta
    max_records: int


TIMEFRAME_BACKFILL_POLICIES: dict[Timeframe, TimeframeBackfillPolicy] = {
    Timeframe.MIN1: TimeframeBackfillPolicy(max_age=timedelta(hours=12), max_records=1_000),
    Timeframe.MIN5: TimeframeBackfillPolicy(max_age=timedelta(days=3), max_records=1_000),
    Timeframe.MIN15: TimeframeBackfillPolicy(max_age=timedelta(days=7), max_records=1_000),
    Timeframe.MIN30: TimeframeBackfillPolicy(max_age=timedelta(days=14), max_records=1_000),
    Timeframe.HOUR1: TimeframeBackfillPolicy(max_age=timedelta(days=30), max_records=1_000),
    Timeframe.HOUR2: TimeframeBackfillPolicy(max_age=timedelta(days=60), max_records=1_000),
    Timeframe.HOUR4: TimeframeBackfillPolicy(max_age=timedelta(days=90), max_records=1_000),
    Timeframe.HOUR12: TimeframeBackfillPolicy(max_age=timedelta(days=180), max_records=1_000),
    Timeframe.DAY1: TimeframeBackfillPolicy(max_age=timedelta(days=365), max_records=1_000),
    Timeframe.DAY7: TimeframeBackfillPolicy(max_age=timedelta(days=730), max_records=500),
    Timeframe.MON1: TimeframeBackfillPolicy(max_age=timedelta(days=1825), max_records=250),
}

DEFAULT_TIMEFRAME_POLICY = TimeframeBackfillPolicy(
    max_age=DEFAULT_MAX_AGE,
    max_records=1_000,
)


def backfill_policy_for(timeframe: Timeframe) -> TimeframeBackfillPolicy:
    return TIMEFRAME_BACKFILL_POLICIES.get(timeframe, DEFAULT_TIMEFRAME_POLICY)

TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.MIN1: 60,
    Timeframe.MIN5: 300,
    Timeframe.MIN15: 900,
    Timeframe.MIN30: 1800,
    Timeframe.HOUR1: 3600,
    Timeframe.HOUR2: 7200,
    Timeframe.HOUR4: 14400,
    Timeframe.HOUR12: 43200,
    Timeframe.DAY1: 86400,
    Timeframe.DAY7: 604800,
    Timeframe.MON1: 2592000,
}


@dataclass
class BackfillReport:
    inserted_by_ticker: dict[str, int] = field(default_factory=dict)
    failed_tickers: dict[str, str] = field(default_factory=dict)
    skipped_tickers: list[str] = field(default_factory=list)

    @property
    def total_inserted(self) -> int:
        return sum(self.inserted_by_ticker.values())


def _candle_to_market_data(candle: Candle) -> MarketData:
    return MarketData(
        volume=candle.volume,
        high_price=candle.high,
        low_price=candle.low,
        close_price=candle.close,
        timestamp=candle.start_time,
    )


class MarketDataBackfillService(ApplicationLoggingMixin):
    def __init__(
            self,
            store: MarketDataStore,
            rest_manager: ExchangeRestManager,
            page_size: int = DEFAULT_BACKFILL_PAGE_SIZE,
            max_records: int = DEFAULT_BACKFILL_MAX_RECORDS,
            max_pages: Optional[int] = None,
    ) -> None:
        self._store = store
        self._rest_manager = rest_manager
        self._page_size = page_size
        self._max_records = max_records
        self._max_pages = (
            max_pages
            if max_pages is not None
            else max(DEFAULT_BACKFILL_MAX_PAGES, (max_records // max(page_size, 1)) + 2)
        )

    def backfill_assets(
            self,
            assets: Iterable[Asset],
            now_epoch: Optional[float] = None,
    ) -> BackfillReport:
        end_epoch = time.time() if now_epoch is None else now_epoch
        report = BackfillReport()

        for asset in assets:
            if not asset.enabled:
                report.skipped_tickers.append(asset.ticker_symbol)
                continue

            try:
                inserted = self._backfill_asset(asset, end_epoch)
                report.inserted_by_ticker[asset.ticker_symbol] = inserted
                self.app_logger.info(
                    "Backfilled %d market data observations for %s (%s)",
                    inserted,
                    asset.ticker_symbol,
                    asset.candles_timeframe.value,
                )
            except Exception as exc:  # pylint: disable=broad-except
                report.failed_tickers[asset.ticker_symbol] = str(exc)
                self.app_logger.warning(
                    "Market data backfill failed for %s on %s; continuing boot: %s",
                    asset.ticker_symbol,
                    asset.exchange.value,
                    exc,
                )

        return report

    @staticmethod
    def configure_store_retention(store: MarketDataStore, assets: Iterable[Asset]) -> None:
        base_max_age = store.max_age
        for asset in assets:
            if not asset.enabled:
                continue
            policy = backfill_policy_for(asset.candles_timeframe)
            effective_max_age = (
                max(base_max_age, policy.max_age)
                if base_max_age is not None
                else policy.max_age
            )
            store.set_ticker_max_age(asset.ticker_symbol, effective_max_age)

    def _backfill_asset(self, asset: Asset, end_epoch: float) -> int:
        policy = backfill_policy_for(asset.candles_timeframe)
        effective_max_records = min(self._max_records, policy.max_records)
        if effective_max_records <= 0:
            return 0

        step_seconds = TIMEFRAME_SECONDS.get(asset.candles_timeframe, 60)
        ranges = self._resolve_backfill_ranges(asset.ticker_symbol, end_epoch, step_seconds)
        inserted = 0
        pages_used = 0

        for range_start, range_end in ranges:
            if inserted >= effective_max_records or pages_used >= self._max_pages:
                break
            range_inserted, range_pages = self._backfill_range(
                asset=asset,
                start_epoch=range_start,
                end_epoch=range_end,
                step_seconds=step_seconds,
                remaining_records=effective_max_records - inserted,
                remaining_pages=self._max_pages - pages_used,
            )
            inserted += range_inserted
            pages_used += range_pages

        return inserted

    def _backfill_range(
            self,
            asset: Asset,
            start_epoch: float,
            end_epoch: float,
            step_seconds: int,
            remaining_records: int,
            remaining_pages: int,
    ) -> tuple[int, int]:
        if start_epoch >= end_epoch or remaining_records <= 0 or remaining_pages <= 0:
            return 0, 0

        cursor_end = end_epoch
        inserted = 0
        pages_used = 0

        for _ in range(remaining_pages):
            if cursor_end < start_epoch or inserted >= remaining_records:
                break

            remaining = remaining_records - inserted
            request_limit = min(self._page_size, remaining)
            chunk_span_seconds = max(request_limit - 1, 0) * step_seconds
            chunk_start = max(start_epoch, cursor_end - chunk_span_seconds)

            candles = self._rest_manager.get_candles(
                exchange=asset.exchange.value,
                ticker_symbol=asset.ticker_symbol,
                timeframe=asset.candles_timeframe,
                start_time=chunk_start,
                end_time=cursor_end,
                limit=request_limit,
            )
            pages_used += 1

            if not candles:
                if chunk_start <= start_epoch:
                    break
                cursor_end = chunk_start - step_seconds
                continue

            ordered = sorted(candles, key=lambda candle: candle.start_time)
            for candle in reversed(ordered):
                if inserted >= remaining_records:
                    break
                if start_epoch <= candle.start_time <= end_epoch:
                    if self._store.record_if_absent(asset.ticker_symbol, _candle_to_market_data(candle)):
                        inserted += 1

            oldest_candle_ts = ordered[0].start_time
            next_cursor_end = oldest_candle_ts - step_seconds
            if next_cursor_end >= cursor_end:
                if chunk_start <= start_epoch:
                    break
                cursor_end = chunk_start - step_seconds
                continue
            if chunk_start <= start_epoch and len(ordered) < request_limit:
                break
            cursor_end = next_cursor_end

        return inserted, pages_used

    def _resolve_backfill_ranges(
            self,
            ticker_symbol: str,
            end_epoch: float,
            step_seconds: int,
    ) -> list[tuple[float, float]]:
        effective_max_age = self._store.max_age_for(ticker_symbol)
        max_age = effective_max_age if effective_max_age is not None else DEFAULT_MAX_AGE
        window_start = end_epoch - max_age.total_seconds()
        latest_ts = self._store.latest_timestamp(ticker_symbol)
        earliest_ts = self._store.earliest_timestamp(ticker_symbol)

        if latest_ts is None or earliest_ts is None or latest_ts < window_start:
            return [(window_start, end_epoch)]

        ranges: list[tuple[float, float]] = []
        if float(latest_ts) < end_epoch:
            ranges.append((float(latest_ts), end_epoch))

        older_end = float(earliest_ts) - step_seconds
        if older_end > window_start:
            ranges.append((window_start, older_end))

        return ranges
