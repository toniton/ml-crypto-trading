from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from api.interfaces.backtest_run_spec import (
    BacktestConfigurationSpec,
    BacktestExecutionSpec,
    BacktestMarketDataSpec,
    BacktestPeriodSpec,
)


class WindowMode(str, Enum):
    ROLLING = "rolling"
    EXPANDING = "expanding"


class WalkForwardWindowSpec(BaseModel):
    train_duration_days: Optional[int] = None
    train_candle_count: Optional[int] = None
    test_duration_days: Optional[int] = None
    test_candle_count: Optional[int] = None
    step_size_days: Optional[int] = None
    step_size_candles: Optional[int] = None
    warmup_candle_count: int = 0
    window_mode: WindowMode = WindowMode.ROLLING


class WalkForwardRunSpec(BaseModel):
    ticker_symbol: str
    configuration: BacktestConfigurationSpec = Field(default_factory=BacktestConfigurationSpec)
    data_source: BacktestMarketDataSpec = Field(default_factory=BacktestMarketDataSpec)
    period: Optional[BacktestPeriodSpec] = None
    windows: WalkForwardWindowSpec = Field(default_factory=WalkForwardWindowSpec)
    initial_balance: Decimal = Decimal("10000.0")
    execution: BacktestExecutionSpec = Field(default_factory=BacktestExecutionSpec)
    candidate_weights: Optional[dict[str, float]] = None


class WalkForwardFold(BaseModel):
    fold_index: int
    warmup_start: Optional[datetime] = None
    warmup_end: Optional[datetime] = None
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    status: str = "PENDING"


class FoldMetricsSummary(BaseModel):
    fold_index: int
    train_return_pct: float
    test_return_pct: float
    test_max_drawdown_pct: float
    test_trades_count: int
    test_win_rate_pct: float
    test_profit_factor: float
    baseline_test_return_pct: Optional[float] = None
    equal_weight_test_return_pct: Optional[float] = None


class WalkForwardSummary(BaseModel):
    run_id: str
    ticker_symbol: str
    total_folds: int
    profitable_folds: int
    profitable_fold_ratio: float
    aggregate_oos_return_pct: float
    max_oos_drawdown_pct: float
    walk_forward_efficiency: float
    fold_results: list[FoldMetricsSummary] = Field(default_factory=list)
    verdict: str
