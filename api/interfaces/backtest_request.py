from __future__ import annotations

from dataclasses import field
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionConfiguration:
    latency_ms: float = 500.0
    slippage_ticks: int = 2
    fee_rate: Decimal = Decimal("0.001")


@dataclass(frozen=True)
class MarketDataConfiguration:
    data_source: str
    data_interval: str = "1s"


@dataclass(frozen=True)
class BacktestRequest:
    asset: str
    start_time: datetime
    end_time: datetime
    market_data: MarketDataConfiguration
    configuration: dict[str, Any] = field(default_factory=dict)
    initial_balance: Decimal = Decimal("10000.0")
    execution: ExecutionConfiguration = field(default_factory=ExecutionConfiguration)
