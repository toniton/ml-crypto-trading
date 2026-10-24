from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from api.interfaces.backtest_run_spec import BacktestPeriodSpec

CALCULATION_VERSION = "1.0.0"


class EvidenceStatus(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    WEAK = "WEAK"
    INSUFFICIENT = "INSUFFICIENT"
    INCONCLUSIVE = "INCONCLUSIVE"
    INCOMPARABLE = "INCOMPARABLE"


class ProposalRecommendation(str, Enum):
    ACCEPT_FOR_TESTING = "ACCEPT_FOR_TESTING"
    PROMOTE_TO_APPROVAL = "PROMOTE_TO_APPROVAL"
    REJECT = "REJECT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EvidenceReference(BaseModel):
    experiment_id: Optional[str] = None
    baseline_backtest_id: Optional[str] = None
    candidate_backtest_id: Optional[str] = None
    baseline_walk_forward_id: Optional[str] = None
    candidate_walk_forward_id: Optional[str] = None
    dataset_id: Optional[str] = None

    def to_id_list(self) -> list[str]:
        refs: list[str] = []
        for val in (
                self.experiment_id,
                self.baseline_backtest_id,
                self.candidate_backtest_id,
                self.baseline_walk_forward_id,
                self.candidate_walk_forward_id,
                self.dataset_id,
        ):
            if val:
                refs.append(val)
        return refs


class ComparabilityReport(BaseModel):
    is_comparable: bool = True
    same_ticker: bool = True
    same_period: bool = True
    same_dataset: bool = True
    same_execution_assumptions: bool = True
    same_initial_balance: bool = True
    discrepancies: list[str] = Field(default_factory=list)


class MetricComparison(BaseModel):
    metric_name: str
    baseline_value: Optional[float] = None
    candidate_value: Optional[float] = None
    absolute_delta: Optional[float] = None
    relative_delta_pct: Optional[float] = None
    is_improvement: Optional[bool] = None


class ExpectedBenefitSummary(BaseModel):
    net_return_pct: MetricComparison = MetricComparison(metric_name="net_return_pct")
    expectancy_per_trade: MetricComparison = MetricComparison(
        metric_name="expectancy_per_trade"
    )
    max_drawdown_pct: MetricComparison = MetricComparison(metric_name="max_drawdown_pct")
    profit_factor: MetricComparison = MetricComparison(metric_name="profit_factor")
    win_rate_pct: MetricComparison = MetricComparison(metric_name="win_rate_pct")
    sharpe_ratio: MetricComparison = MetricComparison(metric_name="sharpe_ratio")
    out_of_sample_return_pct: Optional[MetricComparison] = None
    walk_forward_efficiency: Optional[MetricComparison] = None
    trade_frequency_round_trips: MetricComparison = MetricComparison(
        metric_name="trade_frequency_round_trips"
    )
    exposure_time_pct: MetricComparison = MetricComparison(
        metric_name="exposure_time_pct"
    )
    regime_breakdown: dict[str, MetricComparison] = Field(default_factory=dict)


class SampleSizeSummary(BaseModel):
    baseline_trades: int = 0
    candidate_trades: int = 0
    independent_oos_windows: int = 0
    profitable_oos_windows: int = 0
    evaluation_duration_days: float = 0.0
    regimes_covered: list[str] = Field(default_factory=list)
    estimated_required_sample_size: Optional[int] = None
    is_sample_sufficient: bool = False


class ConfidenceInterval(BaseModel):
    metric_name: str
    point_estimate: float
    lower_bound: float
    upper_bound: float
    confidence_level: float = 0.95
    method: str = "paired_t_approx"


class UncertaintyAssessment(BaseModel):
    intervals: list[ConfidenceInterval] = Field(default_factory=list)
    fold_return_std_pct: Optional[float] = None
    multiple_testing_candidates_count: int = 1
    selection_bias_warning: bool = False
    missing_evidence: list[str] = Field(default_factory=list)
    can_distinguish_from_noise: bool = False


class RiskDeltaSummary(BaseModel):
    max_drawdown_pct_delta: Optional[float] = None
    downside_deviation_pct_delta: Optional[float] = None
    annualized_volatility_pct_delta: Optional[float] = None
    peak_exposure_pct_delta: Optional[float] = None
    avg_exposure_pct_delta: Optional[float] = None
    concentration_hhi_delta: Optional[float] = None
    largest_loss_delta: Optional[float] = None
    max_consecutive_losses_delta: Optional[int] = None
    risk_limit_breaches: list[str] = Field(default_factory=list)
    risk_increased: bool = False
    downside_uncertainty_high: bool = True


class EvidenceBasedProposal(BaseModel):
    id: str
    title: str
    ticker_symbol: str
    hypothesis: str
    proposed_changes_summary: str = ""
    baseline_commit: str
    candidate_commit: Optional[str] = None
    candidate_id: Optional[str] = None
    evidence_refs: EvidenceReference = EvidenceReference()
    evaluation_period: Optional[BacktestPeriodSpec] = None
    market_data_provenance: Optional[str] = None
    execution_assumptions: dict[str, Any] = Field(default_factory=dict)
    comparability: ComparabilityReport = ComparabilityReport()
    expected_benefit: ExpectedBenefitSummary = ExpectedBenefitSummary()
    sample_size: SampleSizeSummary = SampleSizeSummary()
    uncertainty: UncertaintyAssessment = UncertaintyAssessment()
    risk_changes: RiskDeltaSummary = RiskDeltaSummary()
    limitations: list[str] = Field(default_factory=list)
    evidence_status: EvidenceStatus = EvidenceStatus.INSUFFICIENT
    recommendation: ProposalRecommendation = ProposalRecommendation.INSUFFICIENT_EVIDENCE
    validation_plan: list[str] = Field(default_factory=list)
    narrative_summary: str = ""
    calculation_version: str = CALCULATION_VERSION
    triggered_by: Optional[dict[str, Any]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GenerateExperimentProposalRequest(BaseModel):
    candidate_id: str
    hypothesis: Optional[str] = None
    title: Optional[str] = None
    triggered_by: Optional[dict[str, Any]] = None


class GenerateCommitProposalRequest(BaseModel):
    ticker_symbol: str
    baseline_commit: str
    candidate_commit: Optional[str] = None
    hypothesis: Optional[str] = None
    title: Optional[str] = None
    baseline_backtest_id: Optional[str] = None
    candidate_backtest_id: Optional[str] = None
    baseline_walk_forward_id: Optional[str] = None
    candidate_walk_forward_id: Optional[str] = None
    triggered_by: Optional[dict[str, Any]] = None
