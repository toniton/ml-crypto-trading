from __future__ import annotations

from dataclasses import field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionConfiguration:
    latency_ms: float = 500.0
    slippage_ticks: int = 2
    fee_rate: Decimal = Decimal("0.001")


class BacktestDataSourceType(str, Enum):
    CSV = "csv"
    MARKET_DATA = "market_data"


@dataclass(frozen=True)
class BacktestDataSourceRequest:
    source_type: BacktestDataSourceType = BacktestDataSourceType.CSV
    source_id: Optional[str] = None
    path: Optional[str] = None


@dataclass(frozen=True)
class BacktestRequest:
    ticker_symbol: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    data_source: BacktestDataSourceRequest = field(default_factory=BacktestDataSourceRequest)
    initial_balance: Decimal = Decimal("10000.0")
    execution: ExecutionConfiguration = field(default_factory=ExecutionConfiguration)
