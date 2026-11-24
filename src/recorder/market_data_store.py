from __future__ import annotations

import time
from datetime import timedelta
from threading import Lock
from typing import Iterable, Optional

from api.interfaces.market_data import MarketData

DEFAULT_MAX_AGE = timedelta(hours=12)


class MarketDataStore:
    def __init__(
            self,
            max_age: Optional[timedelta] = DEFAULT_MAX_AGE,
            max_observations: Optional[int] = None,
    ) -> None:
        self._lock = Lock()
        self._max_age = max_age if isinstance(max_age, timedelta) else None
        self._ticker_max_ages: dict[str, timedelta] = {}
        self._max_observations = max_observations
        self._observations: dict[str, dict[int, MarketData]] = {}
        self._latest_timestamp: Optional[int] = None

    @property
    def max_age(self) -> Optional[timedelta]:
        return self._max_age

    def set_max_age(self, max_age: Optional[timedelta]) -> None:
        with self._lock:
            self._max_age = max_age if isinstance(max_age, timedelta) else None

    def set_ticker_max_age(self, ticker_symbol: str, max_age: Optional[timedelta]) -> None:
        with self._lock:
            if isinstance(max_age, timedelta):
                self._ticker_max_ages[ticker_symbol] = max_age
            else:
                self._ticker_max_ages.pop(ticker_symbol, None)

    def max_age_for(self, ticker_symbol: str) -> Optional[timedelta]:
        with self._lock:
            return self._max_age_for_locked(ticker_symbol)

    def _max_age_for_locked(self, ticker_symbol: str) -> Optional[timedelta]:
        return self._ticker_max_ages.get(ticker_symbol, self._max_age)

    def record(self, ticker_symbol: str, market_data: MarketData) -> None:
        timestamp = int(market_data.timestamp)
        with self._lock:
            self._store_locked(ticker_symbol, timestamp, market_data, overwrite=True)

    def record_if_absent(self, ticker_symbol: str, market_data: MarketData) -> bool:
        timestamp = int(market_data.timestamp)
        with self._lock:
            return self._store_locked(ticker_symbol, timestamp, market_data, overwrite=False)

    def _store_locked(
            self,
            ticker_symbol: str,
            timestamp: int,
            market_data: MarketData,
            overwrite: bool,
    ) -> bool:
        by_timestamp = self._observations.setdefault(ticker_symbol, {})
        if not overwrite and timestamp in by_timestamp:
            return False
        by_timestamp[timestamp] = market_data
        self._latest_timestamp = (
            timestamp if self._latest_timestamp is None else max(self._latest_timestamp, timestamp)
        )
        self._enforce_limits_locked(ticker_symbol)
        return True

    def _enforce_limits_locked(self, ticker_symbol: str) -> None:
        if self._latest_timestamp is not None:
            for symbol in list(self._observations):
                effective_max_age = self._max_age_for_locked(symbol)
                if effective_max_age is not None:
                    cutoff = self._latest_timestamp - effective_max_age.total_seconds()
                    self._prune_ticker_before_locked(symbol, cutoff)
        if self._max_observations is not None:
            by_timestamp = self._observations.get(ticker_symbol)
            if by_timestamp is not None:
                while len(by_timestamp) > self._max_observations:
                    del by_timestamp[min(by_timestamp)]

    def earliest_timestamp(self, ticker_symbol: str) -> Optional[int]:
        with self._lock:
            by_timestamp = self._observations.get(ticker_symbol)
            if not by_timestamp:
                return None
            return min(by_timestamp)

    def latest_timestamp(self, ticker_symbol: str) -> Optional[int]:
        with self._lock:
            by_timestamp = self._observations.get(ticker_symbol)
            if not by_timestamp:
                return None
            return max(by_timestamp)

    def export_observations(self) -> dict[str, tuple[MarketData, ...]]:
        with self._lock:
            return {
                ticker_symbol: tuple(by_timestamp[ts] for ts in sorted(by_timestamp))
                for ticker_symbol, by_timestamp in self._observations.items()
                if by_timestamp
            }

    def import_observations(
            self,
            observations_by_ticker: dict[str, Iterable[MarketData]],
            now_epoch: Optional[float] = None,
    ) -> int:
        reference_epoch = time.time() if now_epoch is None else now_epoch
        loaded = 0
        with self._lock:
            for ticker_symbol, items in observations_by_ticker.items():
                effective_max_age = self._max_age_for_locked(ticker_symbol)
                cutoff = (
                    reference_epoch - effective_max_age.total_seconds()
                    if effective_max_age is not None
                    else None
                )
                for market_data in items:
                    timestamp = int(market_data.timestamp)
                    if cutoff is not None and timestamp < cutoff:
                        continue
                    by_timestamp = self._observations.setdefault(ticker_symbol, {})
                    by_timestamp[timestamp] = market_data
                    self._latest_timestamp = (
                        timestamp
                        if self._latest_timestamp is None
                        else max(self._latest_timestamp, timestamp)
                    )
                    loaded += 1
                self._enforce_limits_locked(ticker_symbol)
        return loaded

    def prune(self, cutoff_epoch: float) -> int:
        with self._lock:
            return self._prune_before_locked(cutoff_epoch)

    def _prune_ticker_before_locked(self, ticker_symbol: str, cutoff_epoch: float) -> int:
        by_timestamp = self._observations.get(ticker_symbol)
        if not by_timestamp:
            return 0
        stale = [timestamp for timestamp in by_timestamp if timestamp < cutoff_epoch]
        for timestamp in stale:
            del by_timestamp[timestamp]
        if not by_timestamp:
            del self._observations[ticker_symbol]
        return len(stale)

    def _prune_before_locked(self, cutoff_epoch: float) -> int:
        removed = 0
        for ticker_symbol in list(self._observations):
            removed += self._prune_ticker_before_locked(ticker_symbol, cutoff_epoch)
        return removed

    def count_before(self, cutoff_epoch: float) -> int:
        with self._lock:
            return sum(
                1
                for by_timestamp in self._observations.values()
                for timestamp in by_timestamp
                if timestamp < cutoff_epoch
            )

    def size(self, ticker_symbol: Optional[str] = None) -> int:
        with self._lock:
            if ticker_symbol is not None:
                return len(self._observations.get(ticker_symbol, {}))
            return sum(len(by_timestamp) for by_timestamp in self._observations.values())

    def tickers(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._observations))

    def observations(self, ticker_symbol: str) -> tuple[MarketData, ...]:
        with self._lock:
            by_timestamp = self._observations.get(ticker_symbol, {})
        return tuple(by_timestamp[timestamp] for timestamp in sorted(by_timestamp))

    def dataset_id(self, ticker_symbol: str) -> str:
        return f"recorded:{ticker_symbol}"
