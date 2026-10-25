from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import math

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
    ExecutionConfiguration,
)
from api.interfaces.backtest_run_spec import BacktestPeriodSpec
from api.interfaces.evidence_proposal import (
    ExpectedBenefitSummary,
    MetricComparison,
    SampleSizeSummary,
    VerificationStatus,
)
from src.backtest.domain.session import BacktestSession
from src.proposals.evidence_evaluator import EvidenceEvaluator
from src.proposals.models import CollectedEvidence


def _make_session(
        session_id: str,
        ticker: str = "BTC_USD",
        start_day: int = 1,
        end_day: int = 31,
        path: str = "/data/btc.csv",
        fee_rate: str = "0.001",
        slippage_ticks: int = 2,
        balance: str = "10000.0",
) -> BacktestSession:
    req = BacktestRequest(
        ticker_symbol=ticker,
        start_time=datetime(2026, 1, start_day, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, end_day, tzinfo=timezone.utc),
        data_source=BacktestDataSourceRequest(
            source_type=BacktestDataSourceType.CSV,
            path=path,
        ),
        initial_balance=Decimal(balance),
        execution=ExecutionConfiguration(
            latency_ms=500.0,
            slippage_ticks=slippage_ticks,
            fee_rate=Decimal(fee_rate),
        ),
    )
    return BacktestSession(id=session_id, ticker_symbol=ticker, request=req)


class TestEvidenceEvaluator:
    def test_comparability_passes_on_matching_sessions(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="aaa1111",
            candidate_commit="bbb2222",
            baseline_session=_make_session("bt_base"),
            candidate_session=_make_session("bt_cand"),
        )
        report = EvidenceEvaluator.evaluate_comparability(evidence)

        assert report.is_comparable is True
        assert report.verification_status == VerificationStatus.VERIFIED
        assert report.discrepancies == []

    def test_comparability_detects_fee_and_period_mismatch(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="aaa1111",
            candidate_commit="bbb2222",
            baseline_session=_make_session("bt_base", start_day=1, fee_rate="0.001"),
            candidate_session=_make_session("bt_cand", start_day=5, fee_rate="0.0001"),
        )
        report = EvidenceEvaluator.evaluate_comparability(evidence)

        assert report.is_comparable is False
        assert report.verification_status == VerificationStatus.MISMATCH
        assert report.same_period is False
        assert report.same_execution_assumptions is False
        assert len(report.discrepancies) == 2

    def test_comparability_reports_unknown_status_when_evidence_is_missing(self):
        evidence = CollectedEvidence(
            ticker_symbol="",
            baseline_commit="aaa1111",
            candidate_commit="bbb2222",
        )
        report = EvidenceEvaluator.evaluate_comparability(evidence)

        assert report.is_comparable is False
        assert report.verification_status == VerificationStatus.UNKNOWN
        assert len(report.unknown_checks) == 5
        assert any("Missing session records" in d for d in report.discrepancies)

    def test_expected_benefit_computes_absolute_and_relative_deltas(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="aaa1111",
            candidate_commit="bbb2222",
            baseline_bt_metrics={
                "percentage_return": 10.0,
                "max_drawdown_pct": 8.0,
                "expectancy": 15.0,
                "profit_factor": 1.4,
                "win_rate_pct": 52.0,
                "sharpe_ratio": 1.2,
                "round_trips": 40,
                "behavior": {"exposure_time_pct": 60.0},
                "regime_attribution": {
                    "TRENDING_UP": {"total_trades": 20, "avg_return_pct": 1.2},
                    "RANGING": {"total_trades": 20, "avg_return_pct": -0.3},
                },
            },
            candidate_bt_metrics={
                "percentage_return": 14.5,
                "max_drawdown_pct": 6.0,
                "expectancy": 22.5,
                "profit_factor": 1.75,
                "win_rate_pct": 58.0,
                "sharpe_ratio": 1.65,
                "round_trips": 35,
                "behavior": {"exposure_time_pct": 48.0},
                "regime_attribution": {
                    "TRENDING_UP": {"total_trades": 18, "avg_return_pct": 1.5},
                    "RANGING": {"total_trades": 17, "avg_return_pct": 0.2},
                },
            },
            baseline_wf_run={
                "summary": {
                    "aggregate_oos_return_pct": 6.0,
                    "walk_forward_efficiency": 0.65,
                }
            },
            candidate_wf_run={
                "summary": {
                    "aggregate_oos_return_pct": 9.5,
                    "walk_forward_efficiency": 0.78,
                }
            },
        )
        benefit = EvidenceEvaluator.evaluate_expected_benefit(evidence)

        assert benefit.net_return_pct.absolute_delta == 4.5
        assert benefit.net_return_pct.relative_delta_pct == 45.0
        assert benefit.net_return_pct.is_improvement is True
        assert benefit.max_drawdown_pct.absolute_delta == -2.0
        assert benefit.max_drawdown_pct.is_improvement is True
        assert benefit.out_of_sample_return_pct is not None
        assert benefit.out_of_sample_return_pct.absolute_delta == 3.5
        assert "RANGING" in benefit.regime_breakdown
        assert benefit.regime_breakdown["RANGING"].absolute_delta == 0.5

    def test_sample_size_and_uncertainty_with_multiple_candidates(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="aaa1111",
            candidate_commit="bbb2222",
            total_candidates_tested=6,
            evaluation_period=BacktestPeriodSpec(
                start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2026, 3, 2, tzinfo=timezone.utc),
            ),
            baseline_bt_metrics={
                "percentage_return": 5.0,
                "round_trips": 80,
                "regime_attribution": {
                    "TRENDING_UP": {"total_trades": 40},
                    "TRENDING_DOWN": {"total_trades": 40},
                },
            },
            candidate_bt_metrics={
                "percentage_return": 9.0,
                "round_trips": 75,
                "regime_attribution": {
                    "TRENDING_UP": {"total_trades": 38},
                    "TRENDING_DOWN": {"total_trades": 37},
                },
            },
            baseline_wf_run={
                "summary": {
                    "total_folds": 4,
                    "profitable_folds": 2,
                    "aggregate_oos_return_pct": 4.0,
                    "fold_results": [
                        {"test_return_pct": 1.0},
                        {"test_return_pct": 0.8},
                        {"test_return_pct": 1.2},
                        {"test_return_pct": 1.0},
                    ],
                }
            },
            candidate_wf_run={
                "summary": {
                    "total_folds": 4,
                    "profitable_folds": 4,
                    "aggregate_oos_return_pct": 8.8,
                    "fold_results": [
                        {"test_return_pct": 2.1},
                        {"test_return_pct": 2.0},
                        {"test_return_pct": 2.4},
                        {"test_return_pct": 2.3},
                    ],
                }
            },
        )
        benefit = EvidenceEvaluator.evaluate_expected_benefit(evidence)
        sample_size = EvidenceEvaluator.evaluate_sample_size(evidence)
        uncertainty = EvidenceEvaluator.evaluate_uncertainty(evidence, benefit, sample_size)

        assert sample_size.baseline_trades == 80
        assert sample_size.candidate_trades == 75
        assert sample_size.independent_oos_windows == 4
        assert sample_size.evaluation_duration_days == 60.0
        assert sample_size.calendar_days_observed == 60
        assert sample_size.statistical_unit == "independent_oos_windows"
        assert sample_size.is_heuristic is True
        assert sample_size.regimes_covered == ["TRENDING_DOWN", "TRENDING_UP"]
        assert sample_size.is_sample_sufficient is True
        assert uncertainty.selection_bias_warning is True
        assert uncertainty.multiple_testing_candidates_count == 6
        assert len(uncertainty.intervals) == 1
        assert uncertainty.intervals[0].lower_bound > 0.0
        assert uncertainty.can_distinguish_from_noise is True

    def test_normal_interval_uses_independent_degrees_of_freedom(self):
        ss = SampleSizeSummary(
            candidate_trades=1000,
            independent_oos_windows=4,
            is_sample_sufficient=True,
        )
        benefit = ExpectedBenefitSummary(
            net_return_pct=MetricComparison(
                metric_name="net_return_pct",
                baseline_value=5.0,
                candidate_value=10.0,
                absolute_delta=5.0,
            )
        )
        intervals, _ = EvidenceEvaluator._build_normal_interval(  # pylint: disable=protected-access
            benefit=benefit,
            sample_size=ss,
            fold_std=4.0,
            effective_z=1.96,
        )
        assert len(intervals) == 1
        ci = intervals[0]
        # With sigma=4.0 and df=4 (independent_oos_windows), margin = 1.96 * (4.0 / sqrt(4)) = 1.96 * 2 = 3.92
        # NOT deflated by sqrt(1000) ~ 31.62
        expected_margin = round(1.96 * (4.0 / math.sqrt(4)), 4)
        assert round(ci.upper_bound - ci.point_estimate, 4) == expected_margin

    def test_extract_covered_regimes_excludes_calendar_day_strings(self):
        b_bt = {
            "regime_attribution": {
                "day_2026_01_01": {"total_trades": 10},
                "TRENDING_UP": {"total_trades": 15},
            }
        }
        c_bt = {
            "regime_attribution": {
                "day_2026_01_02": {"total_trades": 12},
                "RANGING": {"total_trades": 8},
            }
        }
        regimes = EvidenceEvaluator._extract_covered_regimes(b_bt, c_bt)  # pylint: disable=protected-access
        assert "day_2026_01_01" not in regimes
        assert "day_2026_01_02" not in regimes
        assert regimes == ["RANGING", "TRENDING_UP"]

    def test_risk_changes_flags_increased_drawdown_and_limit_breach(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="aaa1111",
            candidate_commit="bbb2222",
            baseline_config={"portfolio": {"max_drawdown_pct": 15.0}},
            baseline_bt_metrics={
                "max_drawdown_pct": 7.0,
                "portfolio": {"peak_exposure_pct": 40.0},
            },
            candidate_bt_metrics={
                "max_drawdown_pct": 18.5,
                "portfolio": {"peak_exposure_pct": 75.0},
            },
        )
        risk = EvidenceEvaluator.evaluate_risk_changes(evidence)

        assert risk.max_drawdown_pct_delta == 11.5
        assert risk.peak_exposure_pct_delta == 35.0
        assert risk.risk_increased is True
        assert len(risk.risk_limit_breaches) == 1
