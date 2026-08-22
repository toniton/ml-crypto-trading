from typing import Optional

from pydantic import Field
from pydantic.dataclasses import dataclass


@dataclass
class GuardConfig:
    cooldown_timeout: Optional[float] = Field(
        default=None,
        ge=0,
        description="Seconds to wait after a drawdown halt before trading resumes.",
        json_schema_extra={"mutable": True},
    )
    max_drawdown_percentage: Optional[float] = Field(
        default=None,
        gt=0,
        le=1,
        description="Maximum tolerated drawdown fraction (0.60 means 60%) before trading halts.",
        json_schema_extra={"mutable": True},
    )
    max_drawdown_period: Optional[int] = Field(
        default=None,
        ge=1,
        le=10000,
        description="Number of candles over which max drawdown is measured before trading halts.",
        json_schema_extra={"mutable": True},
    )
