from __future__ import annotations

import math
from typing import Any, Optional

from api.interfaces.evidence_proposal import (
    CandidateSearchSummary,
    ComparabilityReport,
    ConfidenceInterval,
    ExpectedBenefitSummary,
    MetricComparison,
    RiskDeltaSummary,
    SampleSizeSummary,
    UncertaintyAssessment,
    VerificationStatus,
)
from src.core.interfaces.execution_status import ExecutionStatus
from src.proposals.models import CollectedEvidence

Z_ALPHA_TWO_SIDED_95 = 1.96
Z_BETA_POWER_80 = 0.8416
DEFAULT_MIN_MEANINGFUL_RETURN_DELTA_PCT = 1.0
DEFAULT_FALLBACK_RETURN_STD_PCT = 5.0
MIN_INDEPENDENT_OOS_FOLDS = 3
MIN_TRADES_BASELINE_FLOOR = 15
DEFAULT_MAX_DRAWDOWN_LIMIT_PCT = 25.0
SIGNIFICANT_DRAWDOWN_INCREASE_PCT = 3.0


class EvidenceEvaluator:
    @classmethod
    def evaluate_comparability(cls, evidence: CollectedEvidence) -> ComparabilityReport:
        report = ComparabilityReport()
        cls._check_session_comparability(evidence, report)
        cls._check_walk_forward_comparability(evidence, report)
        cls._finalize_comparability_status(evidence, report)
        return report

    @staticmethod
    def _check_session_comparability(
            evidence: CollectedEvidence,
            report: ComparabilityReport,
    ) -> None:
        b_sess = evidence.baseline_session
        c_sess = evidence.candidate_session
        if not b_sess or not c_sess:
            return

        if b_sess.ticker_symbol == c_sess.ticker_symbol:
            report.same_ticker = True
            report.verified_checks.append("same_ticker")
        else:
            report.same_ticker = False
            report.discrepancies.append(
                f"Ticker mismatch: baseline={b_sess.ticker_symbol}, candidate={c_sess.ticker_symbol}"
            )

        if (
                b_sess.request.start_time == c_sess.request.start_time
                and b_sess.request.end_time == c_sess.request.end_time
        ):
            report.same_period = True
            report.verified_checks.append("same_period")
        else:
            report.same_period = False
            report.discrepancies.append(
                "Evaluation period start_time or end_time differs between baseline and candidate."
            )

        if (
                b_sess.request.data_source.source_type == c_sess.request.data_source.source_type
                and b_sess.request.data_source.path == c_sess.request.data_source.path
        ):
            report.same_dataset = True
            report.verified_checks.append("same_dataset")
        else:
            report.same_dataset = False
            report.discrepancies.append(
                "Market data source or dataset path differs between baseline and candidate."
            )

        if b_sess.request.initial_balance == c_sess.request.initial_balance:
            report.same_initial_balance = True
            report.verified_checks.append("same_initial_balance")
        else:
            report.same_initial_balance = False
            report.discrepancies.append("Initial balance differs between baseline and candidate.")

        b_exec = b_sess.request.execution
        c_exec = c_sess.request.execution
        if (
                b_exec.fee_rate == c_exec.fee_rate
                and b_exec.slippage_ticks == c_exec.slippage_ticks
                and b_exec.latency_ms == c_exec.latency_ms
        ):
            report.same_execution_assumptions = True
            report.verified_checks.append("same_execution_assumptions")
        else:
            report.same_execution_assumptions = False
            report.discrepancies.append(
                "Execution cost assumptions (fees, slippage, or latency) differ."
            )

    @staticmethod
    def _check_walk_forward_comparability(
            evidence: CollectedEvidence,
            report: ComparabilityReport,
    ) -> None:
        b_wf = evidence.baseline_wf_run
        c_wf = evidence.candidate_wf_run
        if not b_wf or not c_wf:
            return
        b_sum = b_wf.get("summary") or {}
        c_sum = c_wf.get("summary") or {}

        if report.same_ticker is None:
            if b_wf.get("ticker_symbol") and b_wf.get("ticker_symbol") == c_wf.get("ticker_symbol"):
                report.same_ticker = True
                report.verified_checks.append("same_ticker")
        elif b_wf.get("ticker_symbol") != c_wf.get("ticker_symbol"):
            report.same_ticker = False
            report.discrepancies.append("Walk-forward ticker symbol mismatch.")

        if (
                b_sum.get("dataset_identity")
                and c_sum.get("dataset_identity")
                and b_sum.get("dataset_identity") != c_sum.get("dataset_identity")
        ):
            report.same_dataset = False
            report.discrepancies.append("Walk-forward dataset identity mismatch.")
        elif (
                report.same_dataset is None
                and b_sum.get("dataset_identity")
                and b_sum.get("dataset_identity") == c_sum.get("dataset_identity")
        ):
            report.same_dataset = True
            report.verified_checks.append("same_dataset")

        if (
                b_sum.get("execution_assumptions")
                and c_sum.get("execution_assumptions")
                and b_sum.get("execution_assumptions") != c_sum.get("execution_assumptions")
        ):
            report.same_execution_assumptions = False
            report.discrepancies.append("Walk-forward execution assumptions mismatch.")
        elif (
                report.same_execution_assumptions is None
                and b_sum.get("execution_assumptions")
                and b_sum.get("execution_assumptions") == c_sum.get("execution_assumptions")
        ):
            report.same_execution_assumptions = True
            report.verified_checks.append("same_execution_assumptions")

    @staticmethod
    def _finalize_comparability_status(
            evidence: CollectedEvidence,
            report: ComparabilityReport,
    ) -> None:
        has_eval_evidence = bool(
            (evidence.baseline_bt_metrics and evidence.candidate_bt_metrics)
            or (evidence.baseline_wf_run and evidence.candidate_wf_run)
        )
        if report.same_ticker is None and evidence.ticker_symbol:
            report.same_ticker = True
            report.verified_checks.append("same_ticker")
        if report.same_execution_assumptions is None and (
                evidence.execution_assumptions or has_eval_evidence
        ):
            report.same_execution_assumptions = True
            report.verified_checks.append("same_execution_assumptions")
        if report.same_period is None and (
                evidence.evaluation_period or has_eval_evidence
        ):
            report.same_period = True
            report.verified_checks.append("same_period")
        if report.same_dataset is None and (
                evidence.dataset_id or has_eval_evidence
        ):
            report.same_dataset = True
            report.verified_checks.append("same_dataset")
        if report.same_initial_balance is None and (
                evidence.execution_assumptions or has_eval_evidence
        ):
            report.same_initial_balance = True
            report.verified_checks.append("same_initial_balance")

        for name, val in [
            ("same_ticker", report.same_ticker),
            ("same_period", report.same_period),
            ("same_dataset", report.same_dataset),
            ("same_execution_assumptions", report.same_execution_assumptions),
            ("same_initial_balance", report.same_initial_balance),
        ]:
            if val is None:
                report.unknown_checks.append(name)

        if report.discrepancies:
            report.verification_status = VerificationStatus.MISMATCH
            report.is_comparable = False
        elif not report.unknown_checks:
            report.verification_status = VerificationStatus.VERIFIED
            report.is_comparable = True
        else:
            report.verification_status = VerificationStatus.UNKNOWN
            report.is_comparable = False
            report.discrepancies.append(
                f"Missing session records: comparability unverified for: {', '.join(report.unknown_checks)}."
            )

    @classmethod
    def evaluate_expected_benefit(cls, evidence: CollectedEvidence) -> ExpectedBenefitSummary:
        b_bt = evidence.baseline_bt_metrics or {}
        c_bt = evidence.candidate_bt_metrics or {}
        oos_return, wfe = cls._evaluate_walk_forward_benefit(evidence)

        return ExpectedBenefitSummary(
            net_pnl=cls._compare_metric(
                "net_pnl",
                cls._extract_float(b_bt, "net_pnl"),
                cls._extract_float(c_bt, "net_pnl"),
                higher_is_better=True,
            ),
            net_return_pct=cls._compare_metric(
                "net_return_pct",
                cls._extract_float(b_bt, "percentage_return"),
                cls._extract_float(c_bt, "percentage_return"),
                higher_is_better=True,
            ),
            expectancy_per_trade=cls._compare_metric(
                "expectancy_per_trade",
                cls._extract_nested_float(b_bt, "expectancy", ("behavior", "expectancy")),
                cls._extract_nested_float(c_bt, "expectancy", ("behavior", "expectancy")),
                higher_is_better=True,
            ),
            max_drawdown_pct=cls._compare_metric(
                "max_drawdown_pct",
                cls._extract_float(b_bt, "max_drawdown_pct"),
                cls._extract_float(c_bt, "max_drawdown_pct"),
                higher_is_better=False,
            ),
            profit_factor=cls._compare_metric(
                "profit_factor",
                cls._extract_nested_float(b_bt, "profit_factor", ("behavior", "profit_factor")),
                cls._extract_nested_float(c_bt, "profit_factor", ("behavior", "profit_factor")),
                higher_is_better=True,
            ),
            win_rate_pct=cls._compare_metric(
                "win_rate_pct",
                cls._extract_nested_float(b_bt, "win_rate_pct", ("behavior", "win_rate_pct")),
                cls._extract_nested_float(c_bt, "win_rate_pct", ("behavior", "win_rate_pct")),
                higher_is_better=True,
            ),
            sharpe_ratio=cls._compare_metric(
                "sharpe_ratio",
                cls._extract_nested_float(b_bt, "sharpe_ratio", ("risk_adjusted", "sharpe_ratio")),
                cls._extract_nested_float(c_bt, "sharpe_ratio", ("risk_adjusted", "sharpe_ratio")),
                higher_is_better=True,
            ),
            out_of_sample_return_pct=oos_return,
            walk_forward_efficiency=wfe,
            trade_frequency_round_trips=cls._compare_metric(
                "trade_frequency_round_trips",
                cls._extract_nested_float(b_bt, "round_trips", ("behavior", "round_trips")),
                cls._extract_nested_float(c_bt, "round_trips", ("behavior", "round_trips")),
                higher_is_better=None,
            ),
            exposure_time_pct=cls._compare_metric(
                "exposure_time_pct",
                cls._extract_nested_float(b_bt, "exposure_time_pct", ("behavior", "exposure_time_pct")),
                cls._extract_nested_float(c_bt, "exposure_time_pct", ("behavior", "exposure_time_pct")),
                higher_is_better=None,
            ),
            regime_breakdown=cls._evaluate_regime_breakdown(b_bt, c_bt),
        )

    @classmethod
    def _evaluate_walk_forward_benefit(
            cls,
            evidence: CollectedEvidence,
    ) -> tuple[Optional[MetricComparison], Optional[MetricComparison]]:
        b_wf_sum = (evidence.baseline_wf_run or {}).get("summary") or {}
        c_wf_sum = (evidence.candidate_wf_run or {}).get("summary") or {}
        if not b_wf_sum and not c_wf_sum:
            return None, None
        oos_return = cls._compare_metric(
            "out_of_sample_return_pct",
            cls._extract_float(b_wf_sum, "aggregate_oos_return_pct"),
            cls._extract_float(c_wf_sum, "aggregate_oos_return_pct"),
            higher_is_better=True,
        )
        wfe = cls._compare_metric(
            "walk_forward_efficiency",
            cls._extract_float(b_wf_sum, "walk_forward_efficiency"),
            cls._extract_float(c_wf_sum, "walk_forward_efficiency"),
            higher_is_better=True,
        )
        return oos_return, wfe

    @classmethod
    def evaluate_sample_size(cls, evidence: CollectedEvidence) -> SampleSizeSummary:
        b_bt = evidence.baseline_bt_metrics or {}
        c_bt = evidence.candidate_bt_metrics or {}
        b_trades = cls._extract_trade_count(b_bt)
        c_trades = cls._extract_trade_count(c_bt)
        oos_windows, profitable_windows = cls._extract_oos_window_counts(evidence)
        regimes_covered = cls._extract_covered_regimes(b_bt, c_bt)
        duration_days = cls._compute_duration_days(evidence)

        fold_std = cls._compute_fold_return_std(evidence)
        required_windows = cls.estimate_required_sample_size(
            sigma=fold_std if fold_std and fold_std > 0 else DEFAULT_FALLBACK_RETURN_STD_PCT,
            delta=DEFAULT_MIN_MEANINGFUL_RETURN_DELTA_PCT,
        )

        is_sufficient, rationale = cls._determine_sample_sufficiency(
            min(b_trades, c_trades) if (b_trades > 0 and c_trades > 0) else 0,
            oos_windows,
            duration_days,
            regimes_covered,
        )

        return SampleSizeSummary(
            baseline_trades=b_trades,
            candidate_trades=c_trades,
            independent_oos_windows=oos_windows,
            profitable_oos_windows=profitable_windows,
            evaluation_duration_days=duration_days,
            calendar_days_observed=int(math.ceil(duration_days)) if duration_days > 0 else 0,
            regimes_covered=regimes_covered,
            estimated_required_sample_size=required_windows,
            statistical_unit="independent_oos_windows",
            is_heuristic=True,
            sufficiency_rationale=rationale,
            is_sample_sufficient=is_sufficient,
        )

    @staticmethod
    def _determine_sample_sufficiency(
            min_trades: int,
            oos_windows: int,
            duration_days: float,
            regimes_covered: list[str],
    ) -> tuple[bool, str]:
        is_narrow_duration = bool(0.0 < duration_days < 2.0)
        is_sufficient = bool(
            min_trades >= MIN_TRADES_BASELINE_FLOOR
            and oos_windows >= MIN_INDEPENDENT_OOS_FOLDS
            and not is_narrow_duration
            and (len(regimes_covered) >= 2 or oos_windows >= MIN_INDEPENDENT_OOS_FOLDS)
        )
        reasons: list[str] = []
        if min_trades < MIN_TRADES_BASELINE_FLOOR:
            reasons.append(
                f"Completed trade count ({min_trades}) is below minimum floor ({MIN_TRADES_BASELINE_FLOOR})."
            )
        if oos_windows < MIN_INDEPENDENT_OOS_FOLDS:
            reasons.append(
                f"Independent test windows ({oos_windows}) below minimum ({MIN_INDEPENDENT_OOS_FOLDS})."
            )
        if is_narrow_duration:
            reasons.append(
                f"Evaluation duration ({duration_days:.1f}d) is narrow (<2d); trades may be correlated."
            )
        if len(regimes_covered) < 2 and oos_windows < MIN_INDEPENDENT_OOS_FOLDS:
            reasons.append("Fewer than 2 distinct market regimes observed.")

        rationale = (
            "Sample satisfies heuristic thresholds across trade count, out-of-sample folds, and evaluation duration."
            if is_sufficient
            else "; ".join(reasons)
        )
        return is_sufficient, rationale

    @classmethod
    def _extract_trade_count(cls, bt_metrics: dict[str, Any]) -> int:
        return int(
            cls._extract_nested_float(bt_metrics, "round_trips", ("behavior", "round_trips"))
            or cls._extract_float(bt_metrics, "total_trades")
            or 0
        )

    @classmethod
    def _extract_oos_window_counts(cls, evidence: CollectedEvidence) -> tuple[int, int]:
        c_wf_sum = (evidence.candidate_wf_run or {}).get("summary") or {}
        oos_windows = int(cls._extract_float(c_wf_sum, "total_folds") or 0)
        profitable_windows = int(cls._extract_float(c_wf_sum, "profitable_folds") or 0)
        if oos_windows == 0 and evidence.candidate_wf_run:
            folds_list = evidence.candidate_wf_run.get("folds") or []
            oos_windows = len(folds_list)
        return oos_windows, profitable_windows

    @staticmethod
    def estimate_required_sample_size(
            sigma: float,
            delta: float,
            z_alpha: float = Z_ALPHA_TWO_SIDED_95,
            z_beta: float = Z_BETA_POWER_80,
    ) -> int:
        if delta <= 0 or sigma <= 0:
            return MIN_TRADES_BASELINE_FLOOR
        raw_n = (((z_alpha + z_beta) * sigma) / delta) ** 2
        return max(int(math.ceil(raw_n)), 1)

    @classmethod
    def evaluate_uncertainty(
            cls,
            evidence: CollectedEvidence,
            benefit: ExpectedBenefitSummary,
            sample_size: SampleSizeSummary,
    ) -> UncertaintyAssessment:
        missing_evidence = cls._collect_missing_evidence(evidence, sample_size)
        fold_std = cls._compute_fold_return_std(evidence)
        candidates_tested = max(evidence.total_candidates_tested, 1)
        selection_bias_warning = candidates_tested > 1
        holdout_validated = bool(evidence.holdout_validated)
        if selection_bias_warning and not holdout_validated:
            missing_evidence.append(
                "Selected across multiple candidates without independent holdout dataset validation; "
                "threshold adjustment alone cannot rule out data-mining selection bias."
            )
        effective_z = (
            Z_ALPHA_TWO_SIDED_95 + 0.35 * math.log(candidates_tested)
            if selection_bias_warning
            else Z_ALPHA_TWO_SIDED_95
        )
        intervals, can_distinguish = cls._compute_uncertainty_intervals(
            evidence, benefit, sample_size, fold_std, effective_z
        )

        search_summary = (
            CandidateSearchSummary(
                search_algorithm=(
                    "heuristic_walk_forward" if evidence.candidate_search_history else "single_candidate"
                ),
                candidates_evaluated_count=candidates_tested,
                top_candidates=evidence.candidate_search_history,
                holdout_dataset_identified=holdout_validated,
            )
            if (candidates_tested > 1 or evidence.candidate_search_history)
            else None
        )

        return UncertaintyAssessment(
            intervals=intervals,
            fold_return_std_pct=round(fold_std, 4) if fold_std is not None else None,
            multiple_testing_candidates_count=candidates_tested,
            selection_bias_warning=selection_bias_warning,
            holdout_validated=holdout_validated,
            candidate_search_summary=search_summary,
            missing_evidence=missing_evidence,
            can_distinguish_from_noise=can_distinguish,
        )

    @classmethod
    def detect_incomplete_or_failed_runs(cls, evidence: CollectedEvidence) -> list[str]:
        failures: list[str] = []
        if (
            evidence.baseline_session is not None
            and evidence.baseline_session.status != ExecutionStatus.COMPLETED
        ):
            failures.append(
                f"Baseline backtest session is incomplete (status={evidence.baseline_session.status.value})."
            )
        if (
            evidence.candidate_session is not None
            and evidence.candidate_session.status != ExecutionStatus.COMPLETED
        ):
            failures.append(
                f"Candidate backtest session is incomplete (status={evidence.candidate_session.status.value})."
            )
        if evidence.baseline_wf_run is not None:
            b_status = evidence.baseline_wf_run.get("status")
            if b_status is not None and str(b_status).upper() not in (
                    "COMPLETED",
                    "EXECUTIONSTATUS.COMPLETED",
            ):
                failures.append(f"Baseline walk-forward run is incomplete (status={b_status}).")
        if evidence.candidate_wf_run is not None:
            c_status = evidence.candidate_wf_run.get("status")
            if c_status is not None and str(c_status).upper() not in (
                    "COMPLETED",
                    "EXECUTIONSTATUS.COMPLETED",
            ):
                failures.append(f"Candidate walk-forward run is incomplete (status={c_status}).")
        return failures

    @classmethod
    def _collect_missing_evidence(
            cls,
            evidence: CollectedEvidence,
            sample_size: SampleSizeSummary,
    ) -> list[str]:
        missing: list[str] = cls.detect_incomplete_or_failed_runs(evidence)
        if not evidence.baseline_bt_metrics:
            missing.append("Baseline backtest metrics are missing.")
        if not evidence.candidate_bt_metrics:
            missing.append("Candidate backtest metrics are missing.")
        if not evidence.baseline_wf_run or not evidence.candidate_wf_run:
            missing.append("Comparable walk-forward out-of-sample runs are missing.")
        if not sample_size.regimes_covered:
            missing.append("Market regime attribution breakdown is unavailable.")
        return missing

    @classmethod
    def _compute_uncertainty_intervals(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            cls,
            evidence: CollectedEvidence,
            benefit: ExpectedBenefitSummary,
            sample_size: SampleSizeSummary,
            fold_std: Optional[float],
            effective_z: float,
    ) -> tuple[list[ConfidenceInterval], bool]:
        fold_diffs = cls._extract_paired_fold_diffs(evidence)
        if len(fold_diffs) >= 2:
            return cls._build_fold_interval(fold_diffs, effective_z, sample_size)

        if benefit.net_return_pct.absolute_delta is not None and sample_size.candidate_trades >= 2:
            return cls._build_normal_interval(benefit, sample_size, fold_std, effective_z)

        return [], False

    @staticmethod
    def _build_fold_interval(
            fold_diffs: list[float],
            effective_z: float,
            sample_size: SampleSizeSummary,
    ) -> tuple[list[ConfidenceInterval], bool]:
        mean_diff = sum(fold_diffs) / len(fold_diffs)
        variance = sum((d - mean_diff) ** 2 for d in fold_diffs) / (len(fold_diffs) - 1)
        margin = effective_z * math.sqrt(variance / len(fold_diffs))
        lower = round(mean_diff - margin, 4)
        interval = ConfidenceInterval(
            metric_name="oos_fold_return_delta_pct",
            point_estimate=round(mean_diff, 4),
            lower_bound=lower,
            upper_bound=round(mean_diff + margin, 4),
            confidence_level=0.95,
            method="paired_walk_forward_fold_t_interval",
        )
        can_dist = bool(lower > 0.0 and sample_size.independent_oos_windows >= MIN_INDEPENDENT_OOS_FOLDS)
        return [interval], can_dist

    @staticmethod
    def _build_normal_interval(
            benefit: ExpectedBenefitSummary,
            sample_size: SampleSizeSummary,
            fold_std: Optional[float],
            effective_z: float,
    ) -> tuple[list[ConfidenceInterval], bool]:
        pt = benefit.net_return_pct.absolute_delta or 0.0
        sigma = fold_std if fold_std and fold_std > 0 else DEFAULT_FALLBACK_RETURN_STD_PCT
        degrees_of_freedom = max(sample_size.independent_oos_windows, 2)
        margin = effective_z * (sigma / math.sqrt(degrees_of_freedom))
        lower = round(pt - margin, 4)
        interval = ConfidenceInterval(
            metric_name="net_return_delta_pct",
            point_estimate=round(pt, 4),
            lower_bound=lower,
            upper_bound=round(pt + margin, 4),
            confidence_level=0.95,
            method="normal_approximation_interval",
        )
        oos_pos = (
            benefit.out_of_sample_return_pct is not None
            and (benefit.out_of_sample_return_pct.absolute_delta or 0.0) > 0.0
        )
        return [interval], bool(lower > 0.0 and sample_size.is_sample_sufficient and oos_pos)

    @classmethod
    def evaluate_risk_changes(cls, evidence: CollectedEvidence) -> RiskDeltaSummary:
        b_bt = evidence.baseline_bt_metrics or {}
        c_bt = evidence.candidate_bt_metrics or {}
        effective_dd_delta = cls._compute_effective_drawdown_delta(evidence, b_bt, c_bt)
        vol_delta = cls._compute_raw_delta(
            cls._extract_nested_float(
                b_bt, "annualized_volatility_pct", ("risk_adjusted", "annualized_volatility_pct")
            ),
            cls._extract_nested_float(
                c_bt, "annualized_volatility_pct", ("risk_adjusted", "annualized_volatility_pct")
            ),
        )
        peak_exp_delta = cls._compute_raw_delta(
            cls._extract_nested_float(b_bt, "peak_exposure_pct", ("portfolio", "peak_exposure_pct")),
            cls._extract_nested_float(c_bt, "peak_exposure_pct", ("portfolio", "peak_exposure_pct")),
        )
        breaches = cls._evaluate_risk_breaches(evidence, c_bt)
        risk_increased = bool(
            (effective_dd_delta is not None and effective_dd_delta > SIGNIFICANT_DRAWDOWN_INCREASE_PCT)
            or (vol_delta is not None and vol_delta > 5.0)
            or (peak_exp_delta is not None and peak_exp_delta > 10.0)
            or len(breaches) > 0
        )

        return RiskDeltaSummary(
            max_drawdown_pct_delta=effective_dd_delta,
            downside_deviation_pct_delta=cls._compute_raw_delta(
                cls._extract_nested_float(b_bt, "downside_deviation_pct", ("risk_adjusted", "downside_deviation_pct")),
                cls._extract_nested_float(c_bt, "downside_deviation_pct", ("risk_adjusted", "downside_deviation_pct")),
            ),
            annualized_volatility_pct_delta=vol_delta,
            peak_exposure_pct_delta=peak_exp_delta,
            avg_exposure_pct_delta=cls._compute_raw_delta(
                cls._extract_nested_float(b_bt, "avg_exposure_pct", ("portfolio", "avg_exposure_pct")),
                cls._extract_nested_float(c_bt, "avg_exposure_pct", ("portfolio", "avg_exposure_pct")),
            ),
            concentration_hhi_delta=cls._compute_raw_delta(
                cls._extract_nested_float(b_bt, "concentration_hhi", ("portfolio", "concentration_hhi")),
                cls._extract_nested_float(c_bt, "concentration_hhi", ("portfolio", "concentration_hhi")),
            ),
            largest_loss_delta=cls._compute_raw_delta(
                cls._extract_nested_float(b_bt, "largest_loss", ("behavior", "largest_loss")),
                cls._extract_nested_float(c_bt, "largest_loss", ("behavior", "largest_loss")),
            ),
            max_consecutive_losses_delta=cls._compute_consecutive_losses_delta(b_bt, c_bt),
            risk_limit_breaches=breaches,
            risk_increased=risk_increased,
            downside_uncertainty_high=bool(
                not evidence.candidate_bt_metrics
                or not evidence.candidate_wf_run
                or effective_dd_delta is None
            ),
        )

    @classmethod
    def _compute_effective_drawdown_delta(
            cls,
            evidence: CollectedEvidence,
            b_bt: dict[str, Any],
            c_bt: dict[str, Any],
    ) -> Optional[float]:
        dd_delta = cls._compute_raw_delta(
            cls._extract_float(b_bt, "max_drawdown_pct"),
            cls._extract_float(c_bt, "max_drawdown_pct"),
        )
        if dd_delta is not None:
            return dd_delta
        b_wf_sum = (evidence.baseline_wf_run or {}).get("summary") or {}
        c_wf_sum = (evidence.candidate_wf_run or {}).get("summary") or {}
        return cls._compute_raw_delta(
            cls._extract_float(b_wf_sum, "max_oos_drawdown_pct"),
            cls._extract_float(c_wf_sum, "max_oos_drawdown_pct"),
        )

    @classmethod
    def _compute_consecutive_losses_delta(
            cls,
            b_bt: dict[str, Any],
            c_bt: dict[str, Any],
    ) -> Optional[int]:
        b_consec = cls._extract_nested_float(
            b_bt, "max_consecutive_losses", ("behavior", "max_consecutive_losses")
        )
        c_consec = cls._extract_nested_float(
            c_bt, "max_consecutive_losses", ("behavior", "max_consecutive_losses")
        )
        if b_consec is None or c_consec is None:
            return None
        return int(c_consec - b_consec)

    @classmethod
    def _evaluate_risk_breaches(
            cls,
            evidence: CollectedEvidence,
            c_bt: dict[str, Any],
    ) -> list[str]:
        breaches: list[str] = []
        max_dd_limit = cls._resolve_max_drawdown_limit(evidence)
        cand_dd = cls._extract_float(c_bt, "max_drawdown_pct")
        c_wf_sum = (evidence.candidate_wf_run or {}).get("summary") or {}
        cand_oos_dd = cls._extract_float(c_wf_sum, "max_oos_drawdown_pct")

        if cand_dd is not None and cand_dd > max_dd_limit:
            breaches.append(
                f"Candidate backtest max drawdown ({cand_dd:.2f}%) exceeds limit ({max_dd_limit:.2f}%)."
            )
        if cand_oos_dd is not None and cand_oos_dd > max_dd_limit:
            breaches.append(
                f"Candidate out-of-sample max drawdown ({cand_oos_dd:.2f}%) exceeds limit ({max_dd_limit:.2f}%)."
            )
        return breaches

    @staticmethod
    def _resolve_max_drawdown_limit(evidence: CollectedEvidence) -> float:
        for cfg in (evidence.candidate_config, evidence.baseline_config):
            if isinstance(cfg, dict):
                portfolio = cfg.get("portfolio") or {}
                limit = portfolio.get("max_drawdown_pct")
                if limit is not None:
                    try:
                        return float(limit)
                    except (TypeError, ValueError):
                        pass
        return DEFAULT_MAX_DRAWDOWN_LIMIT_PCT

    @staticmethod
    def _extract_float(data: dict[str, Any], key: str) -> Optional[float]:
        val = data.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _extract_nested_float(
            cls,
            data: dict[str, Any],
            top_key: str,
            nested_path: tuple[str, str],
    ) -> Optional[float]:
        direct = cls._extract_float(data, top_key)
        if direct is not None:
            return direct
        section = data.get(nested_path[0])
        if isinstance(section, dict):
            return cls._extract_float(section, nested_path[1])
        return None

    @staticmethod
    def _compute_raw_delta(base_val: Optional[float], cand_val: Optional[float]) -> Optional[float]:
        if base_val is None or cand_val is None:
            return None
        return round(cand_val - base_val, 4)

    @staticmethod
    def _compare_metric(
            name: str,
            baseline_val: Optional[float],
            candidate_val: Optional[float],
            higher_is_better: Optional[bool],
    ) -> MetricComparison:
        if baseline_val is None or candidate_val is None:
            return MetricComparison(
                metric_name=name,
                baseline_value=baseline_val,
                candidate_value=candidate_val,
            )
        abs_delta = round(candidate_val - baseline_val, 4)
        rel_delta: Optional[float] = None
        if abs(baseline_val) > 1e-9:
            rel_delta = round((abs_delta / abs(baseline_val)) * 100.0, 2)

        is_imp: Optional[bool] = None
        if higher_is_better is True:
            is_imp = abs_delta > 0.0
        elif higher_is_better is False:
            is_imp = abs_delta < 0.0

        return MetricComparison(
            metric_name=name,
            baseline_value=round(baseline_val, 4),
            candidate_value=round(candidate_val, 4),
            absolute_delta=abs_delta,
            relative_delta_pct=rel_delta,
            is_improvement=is_imp,
        )

    @classmethod
    def _evaluate_regime_breakdown(
            cls,
            b_bt: dict[str, Any],
            c_bt: dict[str, Any],
    ) -> dict[str, MetricComparison]:
        b_reg = b_bt.get("regime_attribution") or {}
        c_reg = c_bt.get("regime_attribution") or {}
        all_regimes = sorted(set(b_reg.keys()) | set(c_reg.keys()))
        breakdown: dict[str, MetricComparison] = {}
        for reg in all_regimes:
            b_entry = b_reg.get(reg) or {}
            c_entry = c_reg.get(reg) or {}
            b_val = cls._extract_float(b_entry, "avg_return_pct")
            c_val = cls._extract_float(c_entry, "avg_return_pct")
            if b_val is None and c_val is None:
                b_val = cls._extract_float(b_entry, "net_pnl")
                c_val = cls._extract_float(c_entry, "net_pnl")
            if b_val is not None or c_val is not None:
                breakdown[reg] = cls._compare_metric(
                    f"regime_{reg}_return", b_val, c_val, higher_is_better=True
                )
        return breakdown

    @staticmethod
    def _compute_duration_days(evidence: CollectedEvidence) -> float:
        if (
            evidence.evaluation_period
            and evidence.evaluation_period.start_time
            and evidence.evaluation_period.end_time
        ):
            delta = evidence.evaluation_period.end_time - evidence.evaluation_period.start_time
            return round(max(delta.total_seconds() / 86400.0, 0.0), 2)

        if evidence.baseline_session:
            req = evidence.baseline_session.request
            if req.start_time and req.end_time:
                delta = req.end_time - req.start_time
                return round(max(delta.total_seconds() / 86400.0, 0.0), 2)
        return 0.0

    @staticmethod
    def _extract_covered_regimes(b_bt: dict[str, Any], c_bt: dict[str, Any]) -> list[str]:
        covered: set[str] = set()
        for bt in (b_bt, c_bt):
            reg_map = bt.get("regime_attribution") or {}
            for reg_name, metrics in reg_map.items():
                if not reg_name or reg_name.startswith("day_"):
                    continue
                if isinstance(metrics, dict) and int(metrics.get("total_trades") or 0) > 0:
                    covered.add(reg_name)
        return sorted(covered)

    @classmethod
    def _extract_paired_fold_diffs(cls, evidence: CollectedEvidence) -> list[float]:
        b_folds = cls._extract_fold_returns(evidence.baseline_wf_run)
        c_folds = cls._extract_fold_returns(evidence.candidate_wf_run)
        if b_folds and c_folds and len(b_folds) == len(c_folds):
            return [round(c - b, 4) for b, c in zip(b_folds, c_folds)]
        if c_folds and len(c_folds) >= 2:
            b_summary = (evidence.baseline_wf_run or {}).get("summary") or {}
            b_avg = cls._extract_float(b_summary, "aggregate_oos_return_pct") or 0.0
            per_fold_base = b_avg / len(c_folds) if b_avg else 0.0
            return [round(c - per_fold_base, 4) for c in c_folds]
        return []

    @classmethod
    def _compute_fold_return_std(cls, evidence: CollectedEvidence) -> Optional[float]:
        c_folds = cls._extract_fold_returns(evidence.candidate_wf_run)
        if len(c_folds) < 2:
            return None
        mean_val = sum(c_folds) / len(c_folds)
        variance = sum((x - mean_val) ** 2 for x in c_folds) / (len(c_folds) - 1)
        return math.sqrt(variance)

    @classmethod
    def _extract_fold_returns(cls, wf_run: Optional[dict[str, Any]]) -> list[float]:
        if not wf_run:
            return []
        summary = wf_run.get("summary") or {}
        fold_results = summary.get("fold_results") or summary.get("folds") or wf_run.get("folds") or []
        returns: list[float] = []
        for f in fold_results:
            if isinstance(f, dict):
                val = cls._extract_float(f, "test_return_pct")
                if val is None:
                    val = cls._extract_float(f, "out_of_sample_return_pct")
                if val is None and isinstance(f.get("test_metrics"), dict):
                    val = cls._extract_float(f["test_metrics"], "percentage_return")
                if val is not None:
                    returns.append(val)
        return returns
