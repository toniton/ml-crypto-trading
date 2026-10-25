from __future__ import annotations

from typing import Optional
import uuid

from api.interfaces.evidence_proposal import (
    CALCULATION_VERSION,
    ComparabilityReport,
    EvidenceBasedProposal,
    EvidenceReference,
    EvidenceStatus,
    ExpectedBenefitSummary,
    ProposalRecommendation,
    RiskDeltaSummary,
    SampleSizeSummary,
    UncertaintyAssessment,
    VerificationStatus,
)
from src.proposals.evidence_evaluator import (
    EvidenceEvaluator,
    MIN_INDEPENDENT_OOS_FOLDS,
)
from src.proposals.markdown_formatter import ProposalMarkdownFormatter, RECOMMENDATION_LABELS
from src.proposals.models import CollectedEvidence


class ProposalValidator:
    @classmethod
    def build_and_validate_proposal(
            cls,
            evidence: CollectedEvidence,
            proposal_id: str | None = None,
    ) -> EvidenceBasedProposal:
        comparability = EvidenceEvaluator.evaluate_comparability(evidence)
        benefit = EvidenceEvaluator.evaluate_expected_benefit(evidence)
        sample_size = EvidenceEvaluator.evaluate_sample_size(evidence)
        uncertainty = EvidenceEvaluator.evaluate_uncertainty(evidence, benefit, sample_size)
        risk_changes = EvidenceEvaluator.evaluate_risk_changes(evidence)

        status, recommendation = cls._determine_verdict(
            evidence, comparability, benefit, sample_size, uncertainty, risk_changes
        )

        proposal = EvidenceBasedProposal(
            id=proposal_id or f"prop_val_{uuid.uuid4().hex[:10]}",
            title=evidence.title or cls._default_title(evidence),
            ticker_symbol=evidence.ticker_symbol,
            hypothesis=evidence.hypothesis or cls._default_hypothesis(evidence),
            proposed_changes_summary=cls._summarize_changes(evidence),
            baseline_commit=evidence.baseline_commit,
            candidate_commit=evidence.candidate_commit,
            candidate_id=evidence.candidate_id,
            evidence_refs=cls._build_evidence_refs(evidence),
            evaluation_period=evidence.evaluation_period,
            market_data_provenance=evidence.market_data_provenance,
            execution_assumptions=evidence.execution_assumptions,
            calculation_version=CALCULATION_VERSION,
            comparability=comparability,
            expected_benefit=benefit,
            sample_size=sample_size,
            uncertainty=uncertainty,
            risk_changes=risk_changes,
            limitations=cls._build_limitations(
                evidence, comparability, benefit, sample_size, uncertainty, risk_changes
            ),
            evidence_status=status,
            recommendation=recommendation,
            validation_plan=cls._build_validation_plan(
                status, recommendation, sample_size, uncertainty, risk_changes
            ),
            narrative_summary=RECOMMENDATION_LABELS.get(recommendation, recommendation.value),
            triggered_by=evidence.triggered_by,
        )
        proposal.narrative_summary = ProposalMarkdownFormatter.format_proposal(proposal)
        return proposal

    @staticmethod
    def _build_evidence_refs(evidence: CollectedEvidence) -> EvidenceReference:
        return EvidenceReference(
            experiment_id=evidence.experiment_id,
            baseline_backtest_id=evidence.baseline_backtest_id,
            candidate_backtest_id=evidence.candidate_backtest_id,
            baseline_walk_forward_id=evidence.baseline_walk_forward_id,
            candidate_walk_forward_id=evidence.candidate_walk_forward_id,
            dataset_id=evidence.dataset_id,
        )

    @staticmethod
    def _build_limitations(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            evidence: CollectedEvidence,
            comparability: ComparabilityReport,
            benefit: ExpectedBenefitSummary,
            sample_size: SampleSizeSummary,
            uncertainty: UncertaintyAssessment,
            risk_changes: RiskDeltaSummary,
    ) -> list[str]:
        limitations: list[str] = []

        for disc in comparability.discrepancies:
            limitations.append(f"Comparability discrepancy: {disc}")

        for missing in uncertainty.missing_evidence:
            limitations.append(missing)

        if sample_size.independent_oos_windows < MIN_INDEPENDENT_OOS_FOLDS:
            limitations.append(
                f"Insufficient out-of-sample walk-forward windows "
                f"({sample_size.independent_oos_windows} observed vs. {MIN_INDEPENDENT_OOS_FOLDS} required)."
            )

        if not sample_size.is_sample_sufficient:
            unit_str = f" {sample_size.statistical_unit}" if sample_size.statistical_unit else ""
            req_n = sample_size.estimated_required_sample_size or 15
            limitations.append(
                f"Sample size ({sample_size.candidate_trades} candidate trades across "
                f"{sample_size.independent_oos_windows} windows) is below the estimated "
                f"threshold ({req_n}{unit_str}) needed to distinguish the expected improvement from noise."
            )

        if len(sample_size.regimes_covered) < 2:
            limitations.append(
                "Evaluation covers fewer than 2 distinct market regimes; performance may be regime-dependent."
            )

        if (
            sample_size.evaluation_duration_days is not None
            and 0.0 < sample_size.evaluation_duration_days < 2.0
        ):
            limitations.append(
                "Evaluation spans a narrow market period (< 2 days); trades are likely correlated "
                "within a single market episode."
            )

        if uncertainty.selection_bias_warning:
            limitations.append(
                f"Multiple strategy candidates ({uncertainty.multiple_testing_candidates_count}) were "
                f"evaluated in this experiment; selection bias and overfitting risk are elevated."
            )

        if (
            risk_changes.risk_increased
            and benefit.net_return_pct.absolute_delta is not None
            and benefit.net_return_pct.absolute_delta > 0
        ):
            limitations.append(
                "Higher candidate return is accompanied by increased drawdown or exposure; "
                "return gain may be driven by higher risk rather than superior edge."
            )

        for breach in risk_changes.risk_limit_breaches:
            limitations.append(f"Risk limit breach: {breach}")

        if not evidence.execution_assumptions:
            limitations.append(
                "Explicit fee, slippage, and latency assumptions were not recorded on the specification."
            )

        return limitations

    @classmethod
    def _evaluate_oos_sample_verdict(
            cls,
            sample_size: SampleSizeSummary,
            uncertainty: UncertaintyAssessment,
            bt_delta: Optional[float],
            oos_delta: Optional[float],
    ) -> tuple[EvidenceStatus, ProposalRecommendation]:
        if sample_size.independent_oos_windows < MIN_INDEPENDENT_OOS_FOLDS:
            narrow_period = bool(
                sample_size.evaluation_duration_days is not None
                and 0.0 < sample_size.evaluation_duration_days < 2.0
            )
            if not narrow_period and bt_delta is not None and bt_delta > 0.0 and sample_size.candidate_trades >= 15:
                return EvidenceStatus.WEAK, ProposalRecommendation.ACCEPT_FOR_TESTING
            return EvidenceStatus.INSUFFICIENT, ProposalRecommendation.INSUFFICIENT_EVIDENCE

        if not sample_size.is_sample_sufficient or not uncertainty.can_distinguish_from_noise:
            if (oos_delta or 0.0) > 0.0 and (bt_delta or 0.0) > 0.0:
                return EvidenceStatus.WEAK, ProposalRecommendation.ACCEPT_FOR_TESTING
            return EvidenceStatus.INSUFFICIENT, ProposalRecommendation.INSUFFICIENT_EVIDENCE

        return EvidenceStatus.SUFFICIENT, ProposalRecommendation.PROMOTE_TO_APPROVAL

    @classmethod
    def _determine_verdict(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-return-statements
            cls,
            evidence: CollectedEvidence,
            comparability: ComparabilityReport,
            benefit: ExpectedBenefitSummary,
            sample_size: SampleSizeSummary,
            uncertainty: UncertaintyAssessment,
            risk_changes: RiskDeltaSummary,
    ) -> tuple[EvidenceStatus, ProposalRecommendation]:
        if comparability.verification_status == VerificationStatus.MISMATCH:
            return EvidenceStatus.INCOMPARABLE, ProposalRecommendation.INSUFFICIENT_EVIDENCE

        if EvidenceEvaluator.detect_incomplete_or_failed_runs(evidence):
            return EvidenceStatus.INSUFFICIENT, ProposalRecommendation.INSUFFICIENT_EVIDENCE

        if risk_changes.risk_limit_breaches:
            status = (
                EvidenceStatus.SUFFICIENT
                if sample_size.is_sample_sufficient
                else EvidenceStatus.WEAK
            )
            return status, ProposalRecommendation.REJECT

        if not comparability.is_comparable or comparability.verification_status == VerificationStatus.UNKNOWN:
            return EvidenceStatus.INSUFFICIENT, ProposalRecommendation.INSUFFICIENT_EVIDENCE

        if not evidence.baseline_bt_metrics or not evidence.candidate_bt_metrics:
            return EvidenceStatus.INSUFFICIENT, ProposalRecommendation.INSUFFICIENT_EVIDENCE

        bt_delta = benefit.net_return_pct.absolute_delta
        oos_comp = benefit.out_of_sample_return_pct
        oos_delta = oos_comp.absolute_delta if oos_comp else None

        if bt_delta is not None and bt_delta <= 0.0 and (oos_delta is None or oos_delta <= 0.0):
            status = (
                EvidenceStatus.SUFFICIENT
                if sample_size.is_sample_sufficient
                else EvidenceStatus.WEAK
            )
            return status, ProposalRecommendation.REJECT

        if oos_delta is not None and oos_delta < 0.0:
            return EvidenceStatus.WEAK, ProposalRecommendation.REJECT

        if risk_changes.risk_increased or (uncertainty.selection_bias_warning and not uncertainty.holdout_validated):
            return EvidenceStatus.WEAK, ProposalRecommendation.ACCEPT_FOR_TESTING

        return cls._evaluate_oos_sample_verdict(sample_size, uncertainty, bt_delta, oos_delta)

    @staticmethod
    def _build_validation_plan(
            status: EvidenceStatus,
            recommendation: ProposalRecommendation,
            sample_size: SampleSizeSummary,
            uncertainty: UncertaintyAssessment,
            risk_changes: RiskDeltaSummary,
    ) -> list[str]:
        plan: list[str] = []

        if status == EvidenceStatus.INCOMPARABLE:
            plan.append(
                "Re-run baseline and candidate backtests on the exact same dataset, date range, "
                "initial balance, and fee/slippage settings."
            )
            return plan

        if recommendation == ProposalRecommendation.REJECT:
            plan.append(
                "Do not promote candidate configuration; archive experiment findings and "
                "revise strategy parameters to respect drawdown and risk constraints."
            )
            return plan

        if sample_size.independent_oos_windows < MIN_INDEPENDENT_OOS_FOLDS:
            plan.append(
                f"Run a walk-forward evaluation with at least {MIN_INDEPENDENT_OOS_FOLDS} "
                f"independent out-of-sample folds using identical fee and slippage assumptions."
            )

        if not sample_size.is_sample_sufficient:
            target_n = sample_size.estimated_required_sample_size or 30
            plan.append(
                f"Extend the historical evaluation window to capture at least {target_n} "
                f"completed trades across multiple market regimes."
            )

        if uncertainty.selection_bias_warning:
            plan.append(
                "Validate the top candidate on a held-out time period not used during "
                "multi-candidate weight selection."
            )

        if risk_changes.downside_uncertainty_high or risk_changes.risk_increased:
            plan.append(
                "Verify stop-loss and portfolio exposure guardrails remain active before any live test."
            )

        plan.append(
            "Require explicit human approval via Rio's configuration approval workflow "
            "before applying any change to live trading."
        )
        return plan

    @staticmethod
    def _default_title(evidence: CollectedEvidence) -> str:
        cand_label = evidence.candidate_name or evidence.candidate_id or "Candidate"
        return f"Adjust {evidence.ticker_symbol} strategy configuration ({cand_label})"

    @staticmethod
    def _default_hypothesis(evidence: CollectedEvidence) -> str:
        if evidence.config_changes:
            paths = ", ".join(c.path for c in evidence.config_changes[:3])
            return (
                f"Modifying {paths} on {evidence.ticker_symbol} may improve risk-adjusted "
                f"net expectancy and out-of-sample stability compared to baseline commit "
                f"{evidence.baseline_commit[:8]}."
            )
        return (
            f"Applying candidate configuration to {evidence.ticker_symbol} may improve "
            f"net expectancy and reduce drawdown relative to baseline {evidence.baseline_commit[:8]}."
        )

    @staticmethod
    def _summarize_changes(evidence: CollectedEvidence) -> str:
        if not evidence.config_changes:
            return "No explicit configuration diff resolved."
        parts = [
            f"{c.path}: {c.old_value!r} -> {c.new_value!r}"
            for c in evidence.config_changes[:5]
        ]
        return "; ".join(parts)
