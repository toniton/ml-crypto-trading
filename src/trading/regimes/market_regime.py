from dataclasses import dataclass
from enum import Enum


class MarketRegime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    ILLIQUID = "ILLIQUID"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeMetrics:
    regime: MarketRegime
    volatility: float
    trend_strength: float
    liquidity: float
    spread: float
