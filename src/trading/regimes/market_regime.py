from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MarketRegime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    ILLIQUID = "ILLIQUID"
    NORMAL = "NORMAL"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def get_exposure_multiplier(cls, regime: MarketRegime | str) -> float:
        val = regime.value if isinstance(regime, MarketRegime) else str(regime)
        if val in (cls.HIGH_VOLATILITY.value,):
            return 0.50
        if val in (cls.TRENDING_DOWN.value,):
            return 0.75
        if val in (cls.ILLIQUID.value, cls.EXTREME.value):
            return 0.125
        return 1.00


@dataclass(frozen=True)
class RegimeMetrics:
    regime: MarketRegime
    volatility: float
    trend_strength: float
    liquidity: float
    spread: float
