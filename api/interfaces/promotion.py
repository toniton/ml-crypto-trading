from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class PromotionLifecycleState(str, Enum):
    EXPERIMENT = "EXPERIMENT"
    READY_FOR_SIMULATION = "READY_FOR_SIMULATION"
    SIMULATION_QUEUED = "SIMULATION_QUEUED"
    SIMULATING = "SIMULATING"
    REPORT_READY = "REPORT_READY"
    PROMOTION_ELIGIBLE = "PROMOTION_ELIGIBLE"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class GateDecision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class GateCheckStatus(str, Enum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"


class GateCheckItem(BaseModel):
    name: str
    status: GateCheckStatus
    message: str
    value: Optional[Any] = None
    threshold: Optional[Any] = None


class GateEvaluationResult(BaseModel):
    gate_name: str
    decision: GateDecision
    checks: list[GateCheckItem] = Field(default_factory=list)
    evaluated_at: Optional[datetime] = None


class SimulatedRunMarketDataSpec(BaseModel):
    ticker_symbol: str
    timeframe: str = "MIN1"
    exchange: str = "SIMULATED"
    duration_hours: int = 24
    started_at: Optional[datetime] = None
    planned_end_at: Optional[datetime] = None
    real_time: bool = True


class SimulatedRunExecutionSpec(BaseModel):
    initial_balance: float = 10000.0
    slippage_ticks: int = 1
    fee_rate: float = 0.001


class CreateSimulatedRunRequest(BaseModel):
    experiment_id: str
    candidate_id: str
    market_data: Optional[SimulatedRunMarketDataSpec] = None
    execution: Optional[SimulatedRunExecutionSpec] = None
    notes: Optional[str] = None


class SimulatedRunRecord(BaseModel):
    run_id: str
    experiment_id: str
    candidate_id: str
    candidate_commit: str
    config_hash: str
    status: PromotionLifecycleState
    market_data_spec: dict[str, Any] = Field(default_factory=dict)
    execution_spec: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SimulationReportSummary(BaseModel):
    net_return_pct: float
    max_drawdown_pct: float
    executed_trades: int
    win_rate_pct: float
    profit_factor: float
    baseline_return_diff_pct: float
    runtime_errors_count: int


class SimulationReportRecord(BaseModel):
    report_id: str
    run_id: str
    config_hash: str
    decision: GateDecision
    summary_metrics: SimulationReportSummary
    report_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class PromoteToMainRequest(BaseModel):
    idempotency_key: str
    experiment_id: str
    candidate_id: str
    approver: str
    approval_notes: Optional[str] = None
    target_ref: str = "refs/heads/main"


class PromotionRecord(BaseModel):
    promotion_id: str
    idempotency_key: str
    experiment_id: str
    candidate_id: str
    source_commit: str
    target_ref: str
    merge_commit_hash: Optional[str] = None
    status: PromotionLifecycleState
    approver: str
    approval_notes: Optional[str] = None
    gate_results: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PromotionAuditEventRecord(BaseModel):
    event_id: str
    promotion_id: Optional[str] = None
    event_type: str
    from_state: Optional[str] = None
    to_state: str
    actor: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
