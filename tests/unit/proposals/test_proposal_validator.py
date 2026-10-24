from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
    ExecutionConfiguration,
)
from api.interfaces.backtest_run_spec import BacktestPeriodSpec
from api.interfaces.evidence_proposal import (
    CALCULATION_VERSION,
    EvidenceStatus,
    ProposalRecommendation,
)
from src.backtest.domain.session import BacktestSession
from src.core.interfaces.execution_status import ExecutionStatus
from src.proposals.models import CollectedEvidence
from src.proposals.proposal_validator import ProposalValidator


def _build_session(session_id: str, fee_rate: str = "0.001") -> BacktestSession:
    return BacktestSession(
        id=session_id,
        ticker_symbol="BTC_USD",
        request=BacktestRequest(
            ticker_symbol="BTC_USD",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 3, 1, tzinfo=timezone.utc),
            data_source=BacktestDataSourceRequest(
                source_type=BacktestDataSourceType.CSV,
                path="/data/btc.csv",
            ),
            initial_balance=Decimal("10000.0"),
            execution=ExecutionConfiguration(
                latency_ms=500.0,
                slippage_ticks=2,
                fee_rate=Decimal(fee_rate),
            ),
        ),
    )


class TestProposalValidator:
    def test_empty_evidence_produces_insufficient_evidence_report(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="abc12345",
            title="Adjust BTC strategy trading window",
            hypothesis=(
                "Restricting trading to a selected market window may improve net "
                "expectancy and reduce exposure during less favourable periods."
            ),
        )
        proposal = ProposalValidator.build_and_validate_proposal(evidence, proposal_id="ebp_test_1")

        assert proposal.evidence_status == EvidenceStatus.INSUFFICIENT
        assert proposal.recommendation == ProposalRecommendation.INSUFFICIENT_EVIDENCE
        assert "Insufficient evidence" in proposal.narrative_summary
        assert "Pending comparable baseline and candidate runs." in proposal.narrative_summary
        assert "Sample size: not yet calculated" in proposal.narrative_summary
        assert "Uncertainty interval: unavailable" in proposal.narrative_summary
        assert "Out-of-sample validation: required" in proposal.narrative_summary
        assert "Do not apply the change to live trading yet." in proposal.narrative_summary

    def test_incomparable_runs_downgrade_to_incomparable_status(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="abc12345",
            candidate_commit="def67890",
            baseline_session=_build_session("bt_1", fee_rate="0.001"),
            candidate_session=_build_session("bt_2", fee_rate="0.0001"),
            baseline_bt_metrics={"percentage_return": 5.0, "round_trips": 50},
            candidate_bt_metrics={"percentage_return": 12.0, "round_trips": 50},
        )
        proposal = ProposalValidator.build_and_validate_proposal(evidence)

        assert proposal.evidence_status == EvidenceStatus.INCOMPARABLE
        assert proposal.recommendation == ProposalRecommendation.INSUFFICIENT_EVIDENCE
        assert any("Comparability discrepancy" in lim for lim in proposal.limitations)

    def test_risk_limit_breach_recommends_reject(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="abc12345",
            candidate_commit="def67890",
            baseline_bt_metrics={"percentage_return": 5.0, "max_drawdown_pct": 8.0, "round_trips": 50},
            candidate_bt_metrics={"percentage_return": 18.0, "max_drawdown_pct": 32.0, "round_trips": 50},
        )
        proposal = ProposalValidator.build_and_validate_proposal(evidence)

        assert proposal.recommendation == ProposalRecommendation.REJECT
        assert len(proposal.risk_changes.risk_limit_breaches) == 1

    def test_backtest_only_without_walk_forward_never_promotes_to_live_approval(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="abc12345",
            candidate_commit="def67890",
            baseline_bt_metrics={"percentage_return": 5.0, "max_drawdown_pct": 6.0, "round_trips": 60},
            candidate_bt_metrics={"percentage_return": 11.0, "max_drawdown_pct": 5.0, "round_trips": 60},
        )
        proposal = ProposalValidator.build_and_validate_proposal(evidence)

        assert proposal.evidence_status == EvidenceStatus.WEAK
        assert proposal.recommendation == ProposalRecommendation.ACCEPT_FOR_TESTING
        assert proposal.recommendation != ProposalRecommendation.PROMOTE_TO_APPROVAL

    def test_sufficient_multi_fold_comparable_evidence_promotes_to_approval(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="abc12345",
            candidate_commit="def67890",
            execution_assumptions={"fee_rate": "0.001", "slippage_ticks": 2},
            baseline_bt_metrics={
                "percentage_return": 6.0,
                "max_drawdown_pct": 7.5,
                "round_trips": 85,
                "regime_attribution": {
                    "TRENDING_UP": {"total_trades": 45},
                    "RANGING": {"total_trades": 40},
                },
            },
            candidate_bt_metrics={
                "percentage_return": 11.0,
                "max_drawdown_pct": 5.5,
                "round_trips": 80,
                "regime_attribution": {
                    "TRENDING_UP": {"total_trades": 42},
                    "RANGING": {"total_trades": 38},
                },
            },
            baseline_wf_run={
                "summary": {
                    "total_folds": 4,
                    "profitable_folds": 2,
                    "aggregate_oos_return_pct": 4.0,
                    "fold_results": [
                        {"test_return_pct": 1.0},
                        {"test_return_pct": 0.9},
                        {"test_return_pct": 1.1},
                        {"test_return_pct": 1.0},
                    ],
                }
            },
            candidate_wf_run={
                "summary": {
                    "total_folds": 4,
                    "profitable_folds": 4,
                    "aggregate_oos_return_pct": 9.2,
                    "fold_results": [
                        {"test_return_pct": 2.3},
                        {"test_return_pct": 2.2},
                        {"test_return_pct": 2.4},
                        {"test_return_pct": 2.3},
                    ],
                }
            },
        )
        p1 = ProposalValidator.build_and_validate_proposal(evidence, proposal_id="ebp_repro")
        p2 = ProposalValidator.build_and_validate_proposal(evidence, proposal_id="ebp_repro")

        assert p1.evidence_status == EvidenceStatus.SUFFICIENT
        assert p1.recommendation == ProposalRecommendation.PROMOTE_TO_APPROVAL
        assert p1.calculation_version == CALCULATION_VERSION
        assert p1.expected_benefit == p2.expected_benefit
        assert p1.sample_size == p2.sample_size
        assert p1.uncertainty == p2.uncertainty
        assert p1.risk_changes == p2.risk_changes

    def test_failed_walk_forward_or_backtest_run_marks_proposal_insufficient(self):
        failed_session = _build_session("bt_failed")
        failed_session.status = ExecutionStatus.FAILED
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="abc12345",
            candidate_commit="def67890",
            baseline_session=_build_session("bt_ok"),
            candidate_session=failed_session,
            baseline_bt_metrics={"percentage_return": 5.0, "round_trips": 50},
            candidate_bt_metrics={"percentage_return": 12.0, "round_trips": 50},
            candidate_wf_run={"status": "FAILED", "summary": {"total_folds": 4}},
        )
        proposal = ProposalValidator.build_and_validate_proposal(evidence)

        assert proposal.evidence_status == EvidenceStatus.INSUFFICIENT
        assert proposal.recommendation == ProposalRecommendation.INSUFFICIENT_EVIDENCE
        assert any("Candidate backtest session is incomplete" in lim for lim in proposal.limitations)
        assert any("Candidate walk-forward run is incomplete" in lim for lim in proposal.limitations)

    def test_single_narrow_period_marks_proposal_insufficient(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="abc12345",
            candidate_commit="def67890",
            evaluation_period=BacktestPeriodSpec(
                start_time=datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
            ),
            baseline_bt_metrics={"percentage_return": 5.0, "round_trips": 30},
            candidate_bt_metrics={"percentage_return": 9.0, "round_trips": 30},
        )
        proposal = ProposalValidator.build_and_validate_proposal(evidence)

        assert proposal.evidence_status == EvidenceStatus.INSUFFICIENT
        assert proposal.recommendation == ProposalRecommendation.INSUFFICIENT_EVIDENCE
        assert any("narrow market period" in lim for lim in proposal.limitations)

    def test_higher_return_with_materially_higher_drawdown_blocks_live_promotion(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="abc12345",
            candidate_commit="def67890",
            execution_assumptions={"fee_rate": "0.001", "slippage_ticks": 2},
            baseline_bt_metrics={
                "percentage_return": 6.0,
                "max_drawdown_pct": 5.0,
                "round_trips": 85,
                "regime_attribution": {
                    "TRENDING_UP": {"total_trades": 45},
                    "RANGING": {"total_trades": 40},
                },
            },
            candidate_bt_metrics={
                "percentage_return": 11.0,
                "max_drawdown_pct": 14.0,
                "round_trips": 80,
                "regime_attribution": {
                    "TRENDING_UP": {"total_trades": 42},
                    "RANGING": {"total_trades": 38},
                },
            },
            baseline_wf_run={
                "summary": {
                    "total_folds": 4,
                    "profitable_folds": 3,
                    "aggregate_oos_return_pct": 4.0,
                    "fold_results": [
                        {"test_return_pct": 1.0},
                        {"test_return_pct": 0.9},
                        {"test_return_pct": 1.1},
                        {"test_return_pct": 1.0},
                    ],
                }
            },
            candidate_wf_run={
                "summary": {
                    "total_folds": 4,
                    "profitable_folds": 4,
                    "aggregate_oos_return_pct": 9.2,
                    "fold_results": [
                        {"test_return_pct": 2.3},
                        {"test_return_pct": 2.2},
                        {"test_return_pct": 2.4},
                        {"test_return_pct": 2.3},
                    ],
                }
            },
        )
        proposal = ProposalValidator.build_and_validate_proposal(evidence)

        assert proposal.risk_changes.risk_increased is True
        assert proposal.recommendation == ProposalRecommendation.ACCEPT_FOR_TESTING
        assert proposal.recommendation != ProposalRecommendation.PROMOTE_TO_APPROVAL
        assert any("accompanied by increased drawdown" in lim for lim in proposal.limitations)
