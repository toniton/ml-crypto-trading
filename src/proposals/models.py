from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from api.interfaces.backtest_run_spec import BacktestPeriodSpec
from src.backtest.domain.session import BacktestSession
from src.vcs.domain.diff import ConfigChange


class CollectedEvidence(BaseModel):
    ticker_symbol: str
    baseline_commit: str
    candidate_commit: Optional[str] = None
    candidate_id: Optional[str] = None
    candidate_name: Optional[str] = None
    experiment_id: Optional[str] = None
    experiment_name: Optional[str] = None
    total_candidates_tested: int = 1
    candidate_search_history: list[dict[str, Any]] = Field(default_factory=list)
    holdout_validated: bool = False
    dataset_id: Optional[str] = None
    baseline_backtest_id: Optional[str] = None
    baseline_walk_forward_id: Optional[str] = None
    candidate_backtest_id: Optional[str] = None
    candidate_walk_forward_id: Optional[str] = None
    baseline_session: Optional[BacktestSession] = None
    candidate_session: Optional[BacktestSession] = None
    baseline_bt_metrics: Optional[dict[str, Any]] = None
    candidate_bt_metrics: Optional[dict[str, Any]] = None
    baseline_wf_run: Optional[dict[str, Any]] = None
    candidate_wf_run: Optional[dict[str, Any]] = None
    config_changes: list[ConfigChange] = Field(default_factory=list)
    baseline_config: Optional[dict[str, Any]] = None
    candidate_config: Optional[dict[str, Any]] = None
    evaluation_period: Optional[BacktestPeriodSpec] = None
    market_data_provenance: Optional[str] = None
    execution_assumptions: dict[str, Any] = Field(default_factory=dict)
    hypothesis: Optional[str] = None
    title: Optional[str] = None
    triggered_by: Optional[dict[str, Any]] = None
