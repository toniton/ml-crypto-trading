from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field

from api.interfaces.backtest_run_spec import (
    BacktestExecutionSpec,
    BacktestMarketDataSpec,
    BacktestPeriodSpec,
)
from api.interfaces.walk_forward import WalkForwardWindowSpec


class ExperimentStatus(str, Enum):
    DRAFT = "DRAFT"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    AGGREGATING = "AGGREGATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TestSelection(str, Enum):
    __test__ = False
    BACKTEST_ONLY = "BACKTEST_ONLY"
    WALK_FORWARD_ONLY = "WALK_FORWARD_ONLY"
    BOTH = "BOTH"


class CandidateType(str, Enum):
    CURRENT_CONFIG = "CURRENT_CONFIG"
    EQUAL_WEIGHT = "EQUAL_WEIGHT"
    PROPOSED_WEIGHTS = "PROPOSED_WEIGHTS"
    RANDOM_CONTROL = "RANDOM_CONTROL"
    LEAVE_ONE_OUT = "LEAVE_ONE_OUT"
    SINGLE_STRATEGY = "SINGLE_STRATEGY"
    CUSTOM_COMBINATION = "CUSTOM_COMBINATION"


class ExperimentCandidate(BaseModel):
    candidate_id: str
    name: str
    candidate_type: CandidateType
    strategy_weights: dict[str, float] = Field(default_factory=dict)
    candidate_commit_hash: Optional[str] = None
    removed_strategy: Optional[str] = None
    random_seed: Optional[int] = None
    description: Optional[str] = None


class ControlPolicySpec(BaseModel):
    enable_equal_weight_baseline: bool = True
    enable_random_pick_control: bool = False
    random_seeds: list[int] = Field(default_factory=lambda: [42])
    enable_leave_one_out_ablations: bool = False


class ExperimentSpec(BaseModel):
    name: str
    ticker_symbol: str
    base_commit_hash: str
    branch_id: str
    test_selection: TestSelection = TestSelection.BOTH
    data_source: BacktestMarketDataSpec = Field(default_factory=BacktestMarketDataSpec)
    period: Optional[BacktestPeriodSpec] = None
    windows: Optional[WalkForwardWindowSpec] = None
    initial_balance: Decimal = Decimal("10000.0")
    execution: BacktestExecutionSpec = Field(default_factory=BacktestExecutionSpec)
    control_policy: ControlPolicySpec = Field(default_factory=ControlPolicySpec)
    candidates: list[ExperimentCandidate] = Field(default_factory=list)


class CandidateRunBinding(BaseModel):
    candidate_id: str
    backtest_session_id: Optional[str] = None
    walk_forward_run_id: Optional[str] = None
    status: str = "PENDING"
    error: Optional[str] = None


class ExperimentRecord(BaseModel):
    experiment_id: str
    name: str
    ticker_symbol: str
    branch_id: str
    base_commit_hash: str
    status: ExperimentStatus = ExperimentStatus.DRAFT
    spec: ExperimentSpec
    run_bindings: list[CandidateRunBinding] = Field(default_factory=list)
    report: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CreateExperimentRequest(BaseModel):
    name: str
    ticker_symbol: str
    test_selection: TestSelection = TestSelection.BOTH
    data_source: BacktestMarketDataSpec = Field(default_factory=BacktestMarketDataSpec)
    period: Optional[BacktestPeriodSpec] = None
    windows: Optional[WalkForwardWindowSpec] = None
    initial_balance: Decimal = Decimal("10000.0")
    execution: BacktestExecutionSpec = Field(default_factory=BacktestExecutionSpec)
    control_policy: ControlPolicySpec = Field(default_factory=ControlPolicySpec)
    source_commit_hash: Optional[str] = None
