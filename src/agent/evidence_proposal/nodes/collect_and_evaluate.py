from __future__ import annotations

from typing import Any, Optional

from api.interfaces.evidence_proposal import GenerateCommitProposalRequest
from src.agent.evidence_proposal.state import EvidenceProposalState
from src.core.interfaces.database_manager import DatabaseManager
from src.proposals.evidence_collector import EvidenceCollector
from src.proposals.models import CollectedEvidence
from src.proposals.proposal_validator import ProposalValidator
from src.vcs.application.service import VCSService


class CollectAndEvaluateNode:
    def __init__(
            self,
            db_manager: Optional[DatabaseManager] = None,
            vcs_service: Optional[VCSService] = None,
    ):
        self._db_manager = db_manager
        self._vcs_service = vcs_service

    def __call__(self, state: EvidenceProposalState) -> dict[str, Any]:
        experiment_id = state.get("experiment_id")
        candidate_id = state.get("candidate_id") or "cand_equal"
        ticker = state.get("ticker_symbol") or "BTC_USD"
        baseline_commit = state.get("baseline_commit") or "HEAD"
        candidate_commit = state.get("candidate_commit")
        user_prompt = state.get("user_prompt") or ""
        route = state.get("request")
        hypothesis = route.goal.objective if route and route.goal else (user_prompt or None)

        collected: Optional[CollectedEvidence] = None

        if self._db_manager:
            collector = EvidenceCollector(
                db_manager=self._db_manager,
                vcs_service=self._vcs_service,
            )
            if experiment_id:
                try:
                    collected = collector.collect_from_experiment(
                        experiment_id=experiment_id,
                        candidate_id=candidate_id,
                        hypothesis=hypothesis,
                        triggered_by={"source": "agent", "prompt": user_prompt},
                    )
                except Exception:  # pylint: disable=broad-except
                    collected = None

            if collected is None:
                try:
                    req = GenerateCommitProposalRequest(
                        ticker_symbol=ticker,
                        baseline_commit=baseline_commit,
                        candidate_commit=candidate_commit,
                        hypothesis=hypothesis,
                        triggered_by={"source": "agent", "prompt": user_prompt},
                    )
                    collected = collector.collect_from_commits(req)
                except Exception:  # pylint: disable=broad-except
                    collected = None

        if collected is None:
            collected = CollectedEvidence(
                ticker_symbol=ticker,
                baseline_commit=baseline_commit,
                candidate_commit=candidate_commit,
                candidate_id=candidate_id,
                experiment_id=experiment_id,
                hypothesis=hypothesis,
                triggered_by={"source": "agent", "prompt": user_prompt},
            )

        proposal = ProposalValidator.build_and_validate_proposal(collected)
        return {
            "collected_evidence": collected,
            "evidence_proposal": proposal,
        }
