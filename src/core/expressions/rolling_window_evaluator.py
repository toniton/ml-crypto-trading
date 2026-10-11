from typing import Callable, Dict, List, Optional

from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData


class RollingWindowEvaluator:
    _SERIES_EXTRACTORS: Dict[str, Callable[[Candle], float]] = {
        "high": lambda c: float(c.high),
        "low": lambda c: float(c.low),
        "close": lambda c: float(c.close),
        "open": lambda c: float(c.open),
        "volume": lambda c: float(c.volume),
    }

    def __init__(self, candles: List[Candle], market_data: Optional[MarketData] = None):
        self._candles = candles
        self._market_data = market_data

    def highest(self, series: str, period: int) -> Optional[float]:
        window_values = self._resolve_window_values(series, period)
        if window_values is None:
            return None
        return max(window_values)

    def lowest(self, series: str, period: int) -> Optional[float]:
        window_values = self._resolve_window_values(series, period)
        if window_values is None:
            return None
        return min(window_values)

    def _resolve_window_values(self, series: str, period: int) -> Optional[List[float]]:
        self._validate_period(period)
        extractor = self._get_series_extractor(series)
        effective_candles = self._get_prior_candles()
        if len(effective_candles) < period:
            return None
        window = effective_candles[-period:]
        return [extractor(candle) for candle in window]

    @classmethod
    def _validate_period(cls, period: int) -> None:
        if not isinstance(period, int) or isinstance(period, bool) or period <= 0:
            raise ValueError(f"Period must be a positive integer, got {period}")

    @classmethod
    def _get_series_extractor(cls, series: str) -> Callable[[Candle], float]:
        if series not in cls._SERIES_EXTRACTORS:
            supported = ", ".join(sorted(cls._SERIES_EXTRACTORS.keys()))
            raise ValueError(f"Unsupported series '{series}'. Supported series are: {supported}")
        return cls._SERIES_EXTRACTORS[series]

    def _get_prior_candles(self) -> List[Candle]:
        if not self._candles:
            return []
        if self._is_active_candle(self._candles[-1]):
            return self._candles[:-1]
        return self._candles

    def _is_active_candle(self, candle: Candle) -> bool:
        if self._market_data is None:
            return False

        if self._market_data.timestamp is not None and float(self._market_data.timestamp) > 0:
            if float(candle.start_time) >= float(self._market_data.timestamp):
                return True

        if (
                float(candle.close) == float(self._market_data.close_price)
                and float(candle.high) == float(self._market_data.high_price)
                and float(candle.low) == float(self._market_data.low_price)
        ):
            return True

        return False
