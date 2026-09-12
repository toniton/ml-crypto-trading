from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BacktestConfigurationSourceType(str, Enum):
    VCS = "vcs"
    CURRENT = "current"


class BacktestDataSourceType(str, Enum):
    CSV = "csv"
    RECORDED_MARKET_DATA = "recorded_market_data"
    MARKET_DATA = "market_data"


class BacktestConfigurationSpec(BaseModel):
    source_type: BacktestConfigurationSourceType = BacktestConfigurationSourceType.VCS
    vcs_commit_hash: Optional[str] = Field(default=None, description="VCS commit hash to checkout configuration from")


class BacktestMarketDataSpec(BaseModel):
    source_type: BacktestDataSourceType = BacktestDataSourceType.RECORDED_MARKET_DATA
    dataset_id: Optional[str] = Field(default=None, description="Identifier of uploaded CSV dataset")
    path: Optional[str] = Field(default=None, description="Absolute or relative file path to CSV")


class BacktestPeriodSpec(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class BacktestExecutionSpec(BaseModel):
    latency_ms: float = 500.0
    slippage_ticks: int = 2
    fee_rate: Decimal = Decimal("0.001")


class BacktestRunSpec(BaseModel):
    ticker_symbol: str
    configuration: BacktestConfigurationSpec = Field(default_factory=BacktestConfigurationSpec)
    data_source: BacktestMarketDataSpec = Field(default_factory=BacktestMarketDataSpec)
    period: Optional[BacktestPeriodSpec] = None
    initial_balance: Decimal = Decimal("10000.0")
    execution: BacktestExecutionSpec = Field(default_factory=BacktestExecutionSpec)
