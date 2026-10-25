from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid
from typing import Any, Optional

from api.interfaces.backtest_run_spec import BacktestPeriodSpec
import api.interfaces.evidence_proposal as ep
from api.interfaces.trade import Trade
from src.proposals.evidence_evaluator import (
    EvidenceEvaluator,
    MIN_TRADES_BASELINE_FLOOR,
)
from src.proposals.markdown_formatter import ProposalMarkdownFormatter
from src.trading.analytics.strategy_optimizer import (
    BaselineComparisonResult,
    StrategyCalibrationRecommendation,
    StrategyOptimizer,
)
from src.vcs.domain.diff import ConfigChange, ConfigurationProposal


class OptimizerProposalBuilder:
    @classmethod
    def build_evidence_proposal(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
            cls,
            ticker_symbol: str,
            current_asset_config: dict[str, Any],
            trades: list[Trade],
            timezone_str: str = "UTC",
            base_commit_hash: Optional[str] = None,
            allow_asset_fallback: bool = False,
            train_ratio: float = 0.7,
            proposal_id: Optional[str] = None,
    ) -> tuple[ConfigurationProposal, ep.EvidenceBasedProposal]:
        config_proposal = StrategyOptimizer.generate_optimization_proposal(
            ticker_symbol=ticker_symbol,
            current_asset_config=current_asset_config,
            trades=trades,
            timezone_str=timezone_str,
            base_commit_hash=base_commit_hash,
            allow_asset_fallback=allow_asset_fallback,
            train_ratio=train_ratio,
        )

        calibrations, _, baseline_eval = StrategyOptimizer.evaluate_candidate_diagnostics(
            current_asset_config, trades, timezone_str, allow_asset_fallback, train_ratio
        )

        benefit = cls._build_expected_benefit(baseline_eval)
        sample_size = cls._build_sample_size(trades, baseline_eval)
        uncertainty = cls._build_uncertainty(calibrations, baseline_eval, sample_size)
        risk_changes = cls._build_risk_changes(baseline_eval)
        status, recommendation = cls._determine_verdict()
        limitations = cls._build_limitations(
            calibrations, baseline_eval, sample_size, risk_changes
        )
        validation_plan = cls._build_validation_plan(risk_changes)

        comparability = ep.ComparabilityReport(
            is_comparable=False,
            discrepancies=[
                "Preliminary diagnostic only: Complete order execution, consensus, "
                "and portfolio constraints not simulated."
            ],
        )

        evidence_proposal = ep.EvidenceBasedProposal(
            id=proposal_id or f"prop_diag_{uuid.uuid4().hex[:10]}",
            title=f"Preliminary Diagnostic: Calibrate {ticker_symbol} strategy weights and trading windows",
            ticker_symbol=ticker_symbol,
            hypothesis=config_proposal.summary,
            proposed_changes_summary=cls._summarize_changes(list(config_proposal.changes)),
            baseline_commit=base_commit_hash or "HEAD",
            candidate_commit=None,
            candidate_id="cand_optimizer_diagnostic",
            evidence_refs=ep.EvidenceReference(),
            evaluation_period=cls._extract_period(trades),
            market_data_provenance="historical_trade_attribution",
            calculation_version=ep.CALCULATION_VERSION,
            execution_assumptions={"diagnostic_mode": "split_sample_attribution_rescaling"},
            comparability=comparability,
            expected_benefit=benefit,
            sample_size=sample_size,
            uncertainty=uncertainty,
            risk_changes=risk_changes,
            limitations=limitations,
            evidence_status=status,
            recommendation=recommendation,
            validation_plan=validation_plan,
            narrative_summary=config_proposal.expected_effect or config_proposal.summary,
            triggered_by={"source": "strategy_optimizer", "diagnostic_mode": "preliminary"},
        )
        evidence_proposal.narrative_summary = ProposalMarkdownFormatter.format_proposal(
            evidence_proposal
        )
        return config_proposal, evidence_proposal

    @staticmethod
    def _build_expected_benefit(
            baseline_eval: Optional[BaselineComparisonResult],
    ) -> ep.ExpectedBenefitSummary:
        if baseline_eval is None:
            return ep.ExpectedBenefitSummary()
        base_m = baseline_eval.baseline_metrics
        prop_m = baseline_eval.proposed_metrics
        return ep.ExpectedBenefitSummary(
            net_pnl=EvidenceEvaluator._compare_metric(  # pylint: disable=protected-access
                "net_pnl", float(base_m.net_pnl), float(prop_m.net_pnl), higher_is_better=True
            ),
            profit_factor=EvidenceEvaluator._compare_metric(  # pylint: disable=protected-access
                "profit_factor", base_m.profit_factor, prop_m.profit_factor, higher_is_better=True
            ),
            win_rate_pct=EvidenceEvaluator._compare_metric(  # pylint: disable=protected-access
                "win_rate_pct", base_m.win_rate_pct, prop_m.win_rate_pct, higher_is_better=True
            ),
            trade_frequency_round_trips=EvidenceEvaluator._compare_metric(  # pylint: disable=protected-access
                "trade_frequency_round_trips",
                float(base_m.trades_count),
                float(prop_m.trades_count),
                higher_is_better=None,
            ),
        )

    @staticmethod
    def _build_sample_size(
            trades: list[Trade],
            baseline_eval: Optional[BaselineComparisonResult],
    ) -> ep.SampleSizeSummary:
        days: set[tuple[int, int, int]] = set()
        for trade in trades:
            dt = datetime.fromtimestamp(trade.entry_timestamp, tz=timezone.utc)
            days.add((dt.year, dt.month, dt.day))

        duration_days: Optional[float] = None
        if len(trades) >= 2:
            min_ts = min(t.entry_timestamp for t in trades)
            max_ts = max(t.exit_timestamp for t in trades)
            duration_days = round(max(0.0, (max_ts - min_ts) / 86400.0), 2)

        oos_count = baseline_eval.out_of_sample_trades_count if baseline_eval else 0
        sufficient = bool(
            len(trades) >= MIN_TRADES_BASELINE_FLOOR
            and len(days) >= 3
            and oos_count >= 5
        )
        rationale = (
            "Heuristic trade count and calendar span satisfied for preliminary attribution diagnostic."
            if sufficient
            else "Insufficient trade observations or calendar span for reliable attribution calibration."
        )
        return ep.SampleSizeSummary(
            baseline_trades=len(trades),
            candidate_trades=oos_count,
            independent_oos_windows=1 if oos_count > 0 else 0,
            profitable_oos_windows=(
                1
                if baseline_eval and baseline_eval.proposed_metrics.net_pnl > Decimal(0)
                else 0
            ),
            evaluation_duration_days=duration_days,
            calendar_days_observed=len(days),
            regimes_covered=[],
            estimated_required_sample_size=MIN_TRADES_BASELINE_FLOOR,
            statistical_unit="trades",
            is_heuristic=True,
            sufficiency_rationale=rationale,
            is_sample_sufficient=sufficient,
        )

    @staticmethod
    def _build_uncertainty(
            calibrations: list[StrategyCalibrationRecommendation],
            baseline_eval: Optional[BaselineComparisonResult],
            sample_size: ep.SampleSizeSummary,
    ) -> ep.UncertaintyAssessment:
        intervals: list[ep.ConfidenceInterval] = []
        for cal in calibrations:
            if cal.total_trades > 0:
                intervals.append(
                    ep.ConfidenceInterval(
                        metric_name=f"{cal.strategy_name}_win_rate_pct",
                        point_estimate=cal.win_rate_pct,
                        lower_bound=round(max(0.0, cal.win_rate_pct - cal.sample_margin_of_error_pct), 2),
                        upper_bound=round(min(100.0, cal.win_rate_pct + cal.sample_margin_of_error_pct), 2),
                        confidence_level=0.95,
                        method="normal_binomial_win_rate_interval",
                    )
                )

        missing = [
            "Preliminary split-sample attribution rescaling does not simulate the full order, "
            "consensus, and portfolio lifecycle; full walk-forward validation is required.",
            "Comparable multi-fold walk-forward out-of-sample runs are missing.",
        ]
        if baseline_eval is None:
            missing.append("Out-of-sample split comparison unavailable (<4 historical trades).")

        return ep.UncertaintyAssessment(
            intervals=intervals,
            fold_return_std_pct=(
                baseline_eval.proposed_metrics.return_volatility if baseline_eval else None
            ),
            multiple_testing_candidates_count=max(len(calibrations), 1),
            selection_bias_warning=len(calibrations) > 1,
            missing_evidence=missing,
            can_distinguish_from_noise=sample_size.is_sample_sufficient,
        )

    @staticmethod
    def _build_risk_changes(
            baseline_eval: Optional[BaselineComparisonResult],
    ) -> ep.RiskDeltaSummary:
        if baseline_eval is None:
            return ep.RiskDeltaSummary(downside_uncertainty_high=True)
        base_m = baseline_eval.baseline_metrics
        prop_m = baseline_eval.proposed_metrics
        return ep.RiskDeltaSummary(
            max_drawdown_pct_delta=round(float(prop_m.max_drawdown - base_m.max_drawdown), 4),
            annualized_volatility_pct_delta=round(
                prop_m.return_volatility - base_m.return_volatility, 4
            ),
            largest_loss_delta=round(float(prop_m.worst_trade_loss - base_m.worst_trade_loss), 4),
            risk_limit_breaches=[],
            downside_uncertainty_high=baseline_eval.out_of_sample_trades_count < 10,
            risk_increased=baseline_eval.risk_increased,
        )

    @staticmethod
    def _determine_verdict(
            _changes: Any = None,
            _baseline_eval: Optional[BaselineComparisonResult] = None,
            _sample_size: Optional[ep.SampleSizeSummary] = None,
            _risk_changes: Optional[ep.RiskDeltaSummary] = None,
    ) -> tuple[ep.EvidenceStatus, ep.ProposalRecommendation]:
        return ep.EvidenceStatus.INSUFFICIENT, ep.ProposalRecommendation.INSUFFICIENT_EVIDENCE

    @staticmethod
    def _build_limitations(
            calibrations: list[StrategyCalibrationRecommendation],
            baseline_eval: Optional[BaselineComparisonResult],
            sample_size: ep.SampleSizeSummary,
            risk_changes: ep.RiskDeltaSummary,
    ) -> list[str]:
        limitations = [
            "Preliminary diagnostic only: weighted trade attribution rescaling does not execute full consensus, "
            "sizing, order execution, or portfolio constraints.",
            "Not a validated proposal: Requires comparative multi-fold backtest or walk-forward experiment "
            "to evaluate true edge.",
        ]
        if len(sample_size.regimes_covered) < 2:
            limitations.append(
                "Trades originate from a single narrow calendar window; observations are likely correlated."
            )
        if any(c.evidence_status == "INSUFFICIENT" for c in calibrations):
            limitations.append(
                "One or more strategy calibrations lack sufficient independent sample size."
            )
        if risk_changes.risk_increased and baseline_eval is not None:
            limitations.append(
                f"Candidate increased out-of-sample max drawdown by +{baseline_eval.drawdown_delta:.2f} "
                f"(candidate {baseline_eval.proposed_metrics.max_drawdown:.2f} vs "
                f"baseline {baseline_eval.baseline_metrics.max_drawdown:.2f})."
            )
        return limitations

    @staticmethod
    def _build_validation_plan(
            risk_changes: ep.RiskDeltaSummary,
            _status: Optional[ep.EvidenceStatus] = None,
            _recommendation: Optional[ep.ProposalRecommendation] = None,
    ) -> list[str]:
        plan = [
            "Execute a full experiment with baseline and candidate configuration commits through "
            "the backtest and multi-fold walk-forward runner.",
            "Collect simulated execution metrics across full order lifecycle, slippage, and portfolio limits.",
            "Evaluate candidate via the authoritative ProposalValidator before seeking configuration approval.",
        ]
        if risk_changes.downside_uncertainty_high:
            plan.append("Verify drawdown and exposure limits on multi-fold out-of-sample runs.")
        plan.append("Require explicit human approval before live configuration activation.")
        return plan

    @staticmethod
    def _summarize_changes(changes: list[ConfigChange]) -> str:
        if not changes:
            return "No configuration changes proposed."
        return "; ".join(
            f"{c.path}: {c.old_value!r} -> {c.new_value!r}" for c in changes[:5]
        )

    @staticmethod
    def _extract_period(trades: list[Trade]) -> Optional[BacktestPeriodSpec]:
        if not trades:
            return None
        start_dt = datetime.fromtimestamp(min(t.entry_timestamp for t in trades), tz=timezone.utc)
        end_dt = datetime.fromtimestamp(max(t.exit_timestamp for t in trades), tz=timezone.utc)
        return BacktestPeriodSpec(start_time=start_dt, end_time=end_dt)
