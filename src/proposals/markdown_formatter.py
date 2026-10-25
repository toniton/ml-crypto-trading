from __future__ import annotations

from api.interfaces.evidence_proposal import (
    EvidenceBasedProposal,
    EvidenceStatus,
    ExpectedBenefitSummary,
    MetricComparison,
    ProposalRecommendation,
    RiskDeltaSummary,
    SampleSizeSummary,
    UncertaintyAssessment,
)

STATUS_LABELS = {
    EvidenceStatus.SUFFICIENT: "Sufficient evidence",
    EvidenceStatus.WEAK: "Weak / partial evidence",
    EvidenceStatus.INSUFFICIENT: "Insufficient evidence",
    EvidenceStatus.INCONCLUSIVE: "Inconclusive evidence",
    EvidenceStatus.INCOMPARABLE: "Incomparable baseline vs. candidate evidence",
}

RECOMMENDATION_LABELS = {
    ProposalRecommendation.PROMOTE_TO_APPROVAL: "Accept for live configuration approval review",
    ProposalRecommendation.ACCEPT_FOR_TESTING: "Accept for further out-of-sample testing",
    ProposalRecommendation.REJECT: "Reject proposed change",
    ProposalRecommendation.INSUFFICIENT_EVIDENCE: (
        "Do not apply the change to live trading yet. Run a comparable backtest followed by "
        "walk-forward validation, evaluate results across relevant regimes, and record the "
        "resulting evidence before reassessing the proposal."
    ),
}


class ProposalMarkdownFormatter:
    @classmethod
    def format_proposal(cls, proposal: EvidenceBasedProposal) -> str:
        status_label = STATUS_LABELS.get(proposal.evidence_status, proposal.evidence_status.value)
        lines: list[str] = [
            f"## Proposal: {proposal.title}",
            "",
            status_label,
            "",
            "### Hypothesis",
            "",
            proposal.hypothesis,
            "",
            "### Expected benefit",
            "",
        ]
        lines.extend(cls._format_expected_benefit_section(proposal.expected_benefit))
        lines.extend(["", "### Evidence quality", ""])
        lines.extend(cls._format_evidence_quality_section(proposal.sample_size, proposal.uncertainty))
        lines.extend(["", "### Risk assessment", ""])
        lines.extend(cls._format_risk_section(proposal.risk_changes))

        if proposal.limitations:
            lines.extend(["", "### Limitations", ""])
            for lim in proposal.limitations:
                lines.append(f"- {lim}")

        if proposal.validation_plan:
            lines.extend(["", "### Validation plan", ""])
            for step in proposal.validation_plan:
                lines.append(f"- {step}")

        lines.extend(["", "### Recommendation", ""])
        rec_text = (
            proposal.narrative_summary
            if proposal.narrative_summary
            else RECOMMENDATION_LABELS.get(
                proposal.recommendation, proposal.recommendation.value
            )
        )
        lines.append(rec_text)
        return "\n".join(lines)

    @classmethod
    def _format_expected_benefit_section(cls, benefit: ExpectedBenefitSummary) -> list[str]:
        has_any_benefit = (
            benefit.net_return_pct.candidate_value is not None
            or benefit.expectancy_per_trade.candidate_value is not None
            or (
                benefit.out_of_sample_return_pct is not None
                and benefit.out_of_sample_return_pct.candidate_value is not None
            )
        )
        if not has_any_benefit:
            return [
                "Pending comparable baseline and candidate runs.",
                "",
                "- Net expectancy: not yet established",
                "- Drawdown improvement: not yet established",
                "- Trading frequency: measure in the next experiment",
            ]

        lines = [
            f"- Net return: {cls._format_metric(benefit.net_return_pct, unit='%')}",
            f"- Net expectancy: {cls._format_metric(benefit.expectancy_per_trade, unit='')}",
            f"- Drawdown improvement: {cls._format_metric(benefit.max_drawdown_pct, unit='%')}",
        ]
        if benefit.out_of_sample_return_pct is not None:
            lines.append(
                f"- Out-of-sample return: "
                f"{cls._format_metric(benefit.out_of_sample_return_pct, unit='%')}"
            )
        lines.append(
            f"- Trading frequency: "
            f"{cls._format_metric(benefit.trade_frequency_round_trips, unit=' trades')}"
        )
        return lines

    @staticmethod
    def _format_evidence_quality_section(
            ss: SampleSizeSummary,
            unc: UncertaintyAssessment,
    ) -> list[str]:
        lines: list[str] = []
        if ss.candidate_trades == 0 and ss.baseline_trades == 0:
            lines.append("- Sample size: not yet calculated")
        else:
            unit_str = f" {ss.statistical_unit}" if ss.statistical_unit else ""
            req_str = (
                f" (estimated minimum required: {ss.estimated_required_sample_size}{unit_str})"
                if ss.estimated_required_sample_size
                else ""
            )
            duration_parts = []
            if ss.evaluation_duration_days:
                duration_parts.append(f"{ss.evaluation_duration_days} days")
            if ss.calendar_days_observed:
                duration_parts.append(f"{ss.calendar_days_observed} sessions")
            span_str = f" across {', '.join(duration_parts)}" if duration_parts else ""
            lines.append(
                f"- Sample size: {ss.candidate_trades} candidate trades vs. "
                f"{ss.baseline_trades} baseline trades{span_str}{req_str}"
            )

        if ss.independent_oos_windows == 0:
            lines.append("- Independent test windows: not yet established")
        else:
            lines.append(
                f"- Independent test windows: {ss.independent_oos_windows} walk-forward folds "
                f"({ss.profitable_oos_windows} profitable)"
            )

        if ss.regimes_covered:
            lines.append(f"- Market regimes covered: {', '.join(ss.regimes_covered)}")

        if not unc.intervals:
            lines.append("- Uncertainty interval: unavailable")
        else:
            ci = unc.intervals[0]
            lines.append(
                f"- Uncertainty interval ({int(ci.confidence_level * 100)}% CI on {ci.metric_name}): "
                f"[{ci.lower_bound:+.2f}, {ci.upper_bound:+.2f}] (point estimate {ci.point_estimate:+.2f})"
            )

        if ss.independent_oos_windows < 3:
            lines.append("- Out-of-sample validation: required")
        else:
            lines.append(
                f"- Out-of-sample validation: completed across {ss.independent_oos_windows} windows"
            )
        return lines

    @staticmethod
    def _format_risk_section(rc: RiskDeltaSummary) -> list[str]:
        if rc.max_drawdown_pct_delta is None and not rc.risk_limit_breaches:
            return [
                "- Assess whether reduced trading frequency also reduces missed opportunities.",
                "- Compare drawdown, exposure, and downside losses.",
                "- Preserve existing portfolio and execution safeguards.",
            ]
        lines: list[str] = []
        if rc.max_drawdown_pct_delta is not None:
            lines.append(f"- Max drawdown delta: {rc.max_drawdown_pct_delta:+.2f}%")
        if rc.peak_exposure_pct_delta is not None:
            lines.append(f"- Peak exposure delta: {rc.peak_exposure_pct_delta:+.2f}%")
        if rc.annualized_volatility_pct_delta is not None:
            lines.append(
                f"- Annualized volatility delta: {rc.annualized_volatility_pct_delta:+.2f}%"
            )
        if rc.downside_uncertainty_high:
            lines.append("- Downside risk uncertainty remains high due to limited out-of-sample data.")
        for breach in rc.risk_limit_breaches:
            lines.append(f"- Risk limit breach: {breach}")
        return lines

    @staticmethod
    def _format_metric(comp: MetricComparison, unit: str = "") -> str:
        if comp.baseline_value is None or comp.candidate_value is None:
            return "not yet established"
        delta_str = f"{comp.absolute_delta:+.2f}{unit}" if comp.absolute_delta is not None else "n/a"
        rel_str = (
            f" ({comp.relative_delta_pct:+.1f}%)"
            if comp.relative_delta_pct is not None
            else ""
        )
        return (
            f"baseline {comp.baseline_value:.2f}{unit} -> "
            f"candidate {comp.candidate_value:.2f}{unit} "
            f"[delta: {delta_str}{rel_str}]"
        )
