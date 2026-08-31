from __future__ import annotations

from threading import Lock

from api.interfaces.market_data import MarketData


class MarketDataStore:
    DEFAULT_MAX_OBSERVATIONS = 1000

    def __init__(self, max_observations: int = DEFAULT_MAX_OBSERVATIONS) -> None:
        self._lock = Lock()
        self._max_observations = max_observations
        self._observations: dict[str, dict[int, MarketData]] = {}

    def record(self, ticker_symbol: str, market_data: MarketData) -> None:
        timestamp = int(market_data.timestamp)
        with self._lock:
            by_timestamp = self._observations.setdefault(ticker_symbol, {})
            by_timestamp[timestamp] = market_data
            while len(by_timestamp) > self._max_observations:
                del by_timestamp[min(by_timestamp)]

    def tickers(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._observations))

    def observations(self, ticker_symbol: str) -> tuple[MarketData, ...]:
        with self._lock:
            by_timestamp = self._observations.get(ticker_symbol, {})
        return tuple(by_timestamp[timestamp] for timestamp in sorted(by_timestamp))

    def dataset_id(self, ticker_symbol: str) -> str:
        return f"recorded:{ticker_symbol}"
