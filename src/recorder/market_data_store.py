from __future__ import annotations

from datetime import timedelta
from threading import Lock
from typing import Optional

from api.interfaces.market_data import MarketData

DEFAULT_MAX_AGE = timedelta(hours=6)


class MarketDataStore:
    def __init__(
            self,
            max_age: Optional[timedelta] = DEFAULT_MAX_AGE,
            max_observations: Optional[int] = None,
    ) -> None:
        self._lock = Lock()
        self._max_age = max_age if isinstance(max_age, timedelta) else None
        self._max_observations = max_observations
        self._observations: dict[str, dict[int, MarketData]] = {}
        self._latest_timestamp: Optional[int] = None

    @property
    def max_age(self) -> Optional[timedelta]:
        return self._max_age

    def set_max_age(self, max_age: Optional[timedelta]) -> None:
        with self._lock:
            self._max_age = max_age if isinstance(max_age, timedelta) else None

    def record(self, ticker_symbol: str, market_data: MarketData) -> None:
        timestamp = int(market_data.timestamp)
        with self._lock:
            by_timestamp = self._observations.setdefault(ticker_symbol, {})
            by_timestamp[timestamp] = market_data
            self._latest_timestamp = (
                timestamp if self._latest_timestamp is None else max(self._latest_timestamp, timestamp)
            )
            if self._max_age is not None:
                cutoff = self._latest_timestamp - self._max_age.total_seconds()
                self._prune_before_locked(cutoff)
            if self._max_observations is not None:
                while len(by_timestamp) > self._max_observations:
                    del by_timestamp[min(by_timestamp)]

    def prune(self, cutoff_epoch: float) -> int:
        with self._lock:
            return self._prune_before_locked(cutoff_epoch)

    def _prune_before_locked(self, cutoff_epoch: float) -> int:
        removed = 0
        for ticker_symbol in list(self._observations):
            by_timestamp = self._observations[ticker_symbol]
            stale = [timestamp for timestamp in by_timestamp if timestamp < cutoff_epoch]
            for timestamp in stale:
                del by_timestamp[timestamp]
                removed += 1
            if not by_timestamp:
                del self._observations[ticker_symbol]
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
