from __future__ import annotations

from api.interfaces.evidence_proposal import ProposalRecommendation
from src.proposals.evidence_evaluator import EvidenceEvaluator
from src.proposals.models import CollectedEvidence
from src.proposals.proposal_validator import ProposalValidator


class TestCandidateSelectionAndHoldout:
    def test_multiple_candidates_without_holdout_emits_warning(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="aaa1111",
            candidate_commit="bbb2222",
            total_candidates_tested=5,
            holdout_validated=False,
            candidate_search_history=[
                {"candidate_id": "cand_1", "score": 1.2},
                {"candidate_id": "cand_2", "score": 2.5},
            ],
            baseline_bt_metrics={"percentage_return": 5.0, "round_trips": 50},
            candidate_bt_metrics={"percentage_return": 12.0, "round_trips": 50},
            baseline_wf_run={"summary": {"total_folds": 4, "profitable_folds": 3}},
            candidate_wf_run={"summary": {"total_folds": 4, "profitable_folds": 4, "aggregate_oos_return_pct": 5.0}},
        )
        benefit = EvidenceEvaluator.evaluate_expected_benefit(evidence)
        sample_size = EvidenceEvaluator.evaluate_sample_size(evidence)
        uncertainty = EvidenceEvaluator.evaluate_uncertainty(evidence, benefit, sample_size)

        assert uncertainty.selection_bias_warning is True
        assert uncertainty.holdout_validated is False
        assert uncertainty.candidate_search_summary is not None
        assert uncertainty.candidate_search_summary.candidates_evaluated_count == 5
        assert any("Selected across multiple candidates" in m for m in uncertainty.missing_evidence)

    def test_multiple_candidates_without_holdout_caps_recommendation_at_testing(self):
        evidence = CollectedEvidence(
            ticker_symbol="BTC_USD",
            baseline_commit="aaa1111",
            candidate_commit="bbb2222",
            total_candidates_tested=8,
            holdout_validated=False,
            execution_assumptions={"fee_rate": "0.001", "slippage_ticks": 2},
            baseline_bt_metrics={"percentage_return": 6.0, "max_drawdown_pct": 5.0, "round_trips": 85},
            candidate_bt_metrics={"percentage_return": 12.0, "max_drawdown_pct": 4.5, "round_trips": 80},
            baseline_wf_run={
                "summary": {
                    "total_folds": 4,
                    "profitable_folds": 4,
                    "aggregate_oos_return_pct": 4.0,
                    "fold_results": [{"test_return_pct": 1.0}] * 4,
                }
            },
            candidate_wf_run={
                "summary": {
                    "total_folds": 4,
                    "profitable_folds": 4,
                    "aggregate_oos_return_pct": 9.2,
                    "fold_results": [{"test_return_pct": 2.3}] * 4,
                }
            },
        )
        proposal = ProposalValidator.build_and_validate_proposal(evidence)

        assert proposal.recommendation == ProposalRecommendation.ACCEPT_FOR_TESTING
        assert proposal.recommendation != ProposalRecommendation.PROMOTE_TO_APPROVAL
