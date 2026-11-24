from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

from api.interfaces.drift import DriftSnapshotResponse


class LifecycleStage(str, Enum):
    DRAFT = "DRAFT"
    BACKTESTED = "BACKTESTED"
    WALK_FORWARD_VERIFIED = "WALK_FORWARD_VERIFIED"
    PAPER_SIMULATED = "PAPER_SIMULATED"
    LIVE = "LIVE"


class GateCheckSummary(BaseModel):
    name: str
    status: Literal["PASSED", "FAILED", "SKIPPED"]
    message: str


class GateSummary(BaseModel):
    gate_name: str
    decision: Literal["PASS", "FAIL", "PENDING"]
    checks: list[GateCheckSummary] = Field(default_factory=list)


class StageMetrics(BaseModel):
    stage: Literal["backtest", "walk_forward_is", "walk_forward_oos", "paper_simulation", "live"]
    label: str
    status: Literal["available", "running", "missing"] = "missing"
    return_pct: Optional[float] = None
    annualized_return_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    win_rate_pct: Optional[float] = None
    profit_factor: Optional[float] = None
    trade_count: Optional[int] = None
    total_fees: Optional[float] = None
    realized_pnl: Optional[float] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    source_run_id: Optional[str] = None
    deep_link: Optional[str] = None


class LifecycleProgress(BaseModel):
    current_stage: LifecycleStage = LifecycleStage.DRAFT
    completed_stages: list[LifecycleStage] = Field(default_factory=list)
    gate_a: Optional[GateSummary] = None
    gate_b: Optional[GateSummary] = None
    active_experiment_id: Optional[str] = None
    active_simulation_id: Optional[str] = None
    can_promote_to_main: bool = False


class RegimePerformanceSlice(BaseModel):
    regime: str
    return_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    win_rate_pct: Optional[float] = None
    trade_count: int = 0
    net_pnl: Optional[float] = None


class StrategyAttributionSlice(BaseModel):
    strategy_name: str
    total_trades: int = 0
    win_rate_pct: float = 0.0
    net_pnl: float = 0.0
    total_fees: float = 0.0
    total_slippage: float = 0.0
    profit_factor: float = 0.0


class StrategyScorecardSummary(BaseModel):
    symbol: str
    venue: str = "default"
    quote_currency: str = "USD"
    branch: str = "main"
    commit_hash: Optional[str] = None
    current_stage: LifecycleStage = LifecycleStage.DRAFT
    live_return_pct: Optional[float] = None
    oos_return_pct: Optional[float] = None
    backtest_return_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    drifted: Optional[bool] = None
    updated_at: Optional[str] = None


class StrategyScorecardResponse(BaseModel):
    symbol: str
    venue: str = "default"
    quote_currency: str = "USD"
    branch: str = "main"
    commit_hash: Optional[str] = None
    commit_message: Optional[str] = None
    generated_at: str
    lifecycle: LifecycleProgress
    stages: list[StageMetrics] = Field(default_factory=list)
    regimes: list[RegimePerformanceSlice] = Field(default_factory=list)
    attribution: list[StrategyAttributionSlice] = Field(default_factory=list)
    latest_drift: Optional[DriftSnapshotResponse] = None


class ScorecardSnapshotSummary(BaseModel):
    snapshot_id: str
    symbol: str
    venue: str = "default"
    quote_currency: str = "USD"
    branch: str = "main"
    commit_hash: Optional[str] = None
    trigger: Literal["manual", "drift_run"] = "manual"
    current_stage: LifecycleStage = LifecycleStage.DRAFT
    live_return_pct: Optional[float] = None
    oos_return_pct: Optional[float] = None
    backtest_return_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    drifted: Optional[bool] = None
    created_at: str


class ScorecardSnapshotRecord(BaseModel):
    snapshot_id: str
    trigger: Literal["manual", "drift_run"] = "manual"
    created_at: str
    scorecard: StrategyScorecardResponse
