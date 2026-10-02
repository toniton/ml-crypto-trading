from typing import List

from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from src.trading.regimes.market_regime import MarketRegime, RegimeMetrics


class MarketRegimeDetector:
    DEFAULT_PERIOD = 20
    HIGH_VOLATILITY_THRESHOLD = 0.03
    LOW_VOLATILITY_THRESHOLD = 0.005
    TREND_THRESHOLD = 0.005
    ILLIQUID_SPREAD_THRESHOLD = 0.05
    MIN_DATA_POINTS = 3

    def __init__(
            self,
            high_volatility_threshold: float = HIGH_VOLATILITY_THRESHOLD,
            low_volatility_threshold: float = LOW_VOLATILITY_THRESHOLD,
            trend_threshold: float = TREND_THRESHOLD,
            illiquid_spread_threshold: float = ILLIQUID_SPREAD_THRESHOLD,
    ):
        self._high_volatility_threshold = high_volatility_threshold
        self._low_volatility_threshold = low_volatility_threshold
        self._trend_threshold = trend_threshold
        self._illiquid_spread_threshold = illiquid_spread_threshold

    def detect(
            self,
            candles: List[Candle],
            market_data: MarketData,
            period: int = DEFAULT_PERIOD,
    ) -> RegimeMetrics:
        close = float(market_data.close_price) if market_data else 0.0
        volatility = self.calculate_volatility(candles, close, period)
        trend_strength = self.calculate_trend_strength(candles, period)
        liquidity = self.calculate_liquidity(candles, market_data, period)
        spread = self.calculate_spread(market_data, close)

        has_sufficient_data = len(candles) >= self.MIN_DATA_POINTS
        regime = self.classify(
            trend_strength=trend_strength,
            volatility=volatility,
            liquidity=liquidity,
            spread=spread,
            has_sufficient_data=has_sufficient_data,
        )

        return RegimeMetrics(
            regime=regime,
            volatility=volatility,
            trend_strength=trend_strength,
            liquidity=liquidity,
            spread=spread,
        )

    def calculate_volatility(self, candles: List[Candle], close: float, period: int = DEFAULT_PERIOD) -> float:
        if not candles or len(candles) <= 1 or close <= 0:
            return 0.0

        n = min(period, len(candles) - 1)
        true_ranges = []
        for i in range(len(candles) - n, len(candles)):
            curr = candles[i]
            prev = candles[i - 1]
            high = float(curr.high)
            low = float(curr.low)
            prev_close = float(prev.close)
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)

        if not true_ranges:
            return 0.0

        atr = sum(true_ranges) / len(true_ranges)
        return atr / close

    def calculate_trend_strength(self, candles: List[Candle], period: int = DEFAULT_PERIOD) -> float:
        if not candles or len(candles) < self.MIN_DATA_POINTS:
            return 0.0

        prices = [float(c.close) for c in candles]
        fast_period = max(2, period // 2)
        slow_period = max(fast_period + 1, min(period, len(prices)))

        if len(prices) < slow_period:
            slow_period = len(prices)
            fast_period = max(2, slow_period // 2)

        fast_ema = self._calculate_ema_value(prices, fast_period)
        slow_ema = self._calculate_ema_value(prices, slow_period)

        if slow_ema <= 0:
            return 0.0

        return (fast_ema - slow_ema) / slow_ema

    def calculate_liquidity(
            self,
            candles: List[Candle],
            market_data: MarketData,
            period: int = DEFAULT_PERIOD,
    ) -> float:
        if market_data and market_data.volume is not None:
            return float(market_data.volume)

        if candles:
            volumes = [
                float(getattr(c, "volume"))
                for c in candles
                if hasattr(c, "volume") and getattr(c, "volume") is not None
            ]
            if volumes:
                n = min(period, len(volumes))
                return sum(volumes[-n:]) / n

        return 0.0

    def calculate_spread(self, market_data: MarketData, close: float) -> float:
        if not market_data or close <= 0:
            return 0.0

        if market_data.bid_price is not None and market_data.ask_price is not None:
            bid = float(market_data.bid_price)
            ask = float(market_data.ask_price)
            if ask >= bid:
                return (ask - bid) / close

        return 0.0

    def classify(
            self,
            trend_strength: float,
            volatility: float,
            liquidity: float,
            spread: float,
            has_sufficient_data: bool = True,
    ) -> MarketRegime:
        if not has_sufficient_data:
            return MarketRegime.UNKNOWN

        if liquidity <= 0.0 or spread >= self._illiquid_spread_threshold:
            return MarketRegime.ILLIQUID

        if volatility >= self._high_volatility_threshold:
            return MarketRegime.HIGH_VOLATILITY

        if trend_strength >= self._trend_threshold:
            return MarketRegime.TRENDING_UP

        if trend_strength <= -self._trend_threshold:
            return MarketRegime.TRENDING_DOWN

        if volatility <= self._low_volatility_threshold:
            return MarketRegime.LOW_VOLATILITY

        return MarketRegime.RANGING

    @staticmethod
    def _calculate_ema_value(prices: List[float], period: int) -> float:
        if not prices or period <= 0:
            return 0.0
        if len(prices) <= period:
            return sum(prices) / len(prices)

        multiplier = 2.0 / (period + 1)
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
