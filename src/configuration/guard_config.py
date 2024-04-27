from typing import Optional

from pydantic.dataclasses import dataclass


@dataclass
class GuardConfig:
    cooldown_timeout: Optional[float]
    max_drawdown_percentage: Optional[float]
    max_drawdown_period: Optional[int]
