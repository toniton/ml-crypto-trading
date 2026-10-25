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

    def _collect_from_experiment(
            self,
            collector: Optional[EvidenceCollector],
            experiment_id: str,
            candidate_id: Optional[str],
            hypothesis: Optional[str],
            user_prompt: str,
    ) -> tuple[Optional[CollectedEvidence], Optional[dict[str, Any]]]:
        if not collector:
            return None, {
                "resolution_status": "EVIDENCE_UNAVAILABLE",
                "status_message": (
                    f"Database manager is unavailable to retrieve experiment '{experiment_id}'."
                ),
            }
        try:
            cid = candidate_id or "cand_1"
            collected = collector.collect_from_experiment(
                experiment_id=experiment_id,
                candidate_id=cid,
                hypothesis=hypothesis,
                triggered_by={"source": "agent", "prompt": user_prompt},
            )
            return collected, None
        except ValueError as exc:
            return None, {
                "resolution_status": "EVIDENCE_UNAVAILABLE",
                "status_message": f"Evidence lookup failed: {exc}",
            }
        except Exception as exc:  # pylint: disable=broad-except
            return None, {
                "resolution_status": "EVIDENCE_UNAVAILABLE",
                "status_message": (
                    f"Failed to retrieve evidence for experiment '{experiment_id}': {exc}"
                ),
            }

    def _collect_from_candidate(
            self,
            collector: Optional[EvidenceCollector],
            state: EvidenceProposalState,
            hypothesis: Optional[str],
            user_prompt: str,
    ) -> tuple[Optional[CollectedEvidence], Optional[dict[str, Any]]]:
        ticker = state.get("ticker_symbol") or ""
        baseline_commit = state.get("baseline_commit") or "HEAD"
        candidate_commit = state.get("candidate_commit")
        candidate_id = state.get("candidate_id")

        if candidate_commit and collector:
            try:
                req = GenerateCommitProposalRequest(
                    ticker_symbol=ticker,
                    baseline_commit=baseline_commit,
                    candidate_commit=candidate_commit,
                    hypothesis=hypothesis,
                    triggered_by={"source": "agent", "prompt": user_prompt},
                )
                return collector.collect_from_commits(req), None
            except Exception as exc:  # pylint: disable=broad-except
                return None, {
                    "resolution_status": "EVIDENCE_UNAVAILABLE",
                    "status_message": (
                        f"Failed to resolve evidence for candidate commit '{candidate_commit}': {exc}"
                    ),
                }

        if candidate_commit or candidate_id:
            collected = CollectedEvidence(
                ticker_symbol=ticker,
                baseline_commit=baseline_commit,
                candidate_commit=candidate_commit,
                candidate_id=candidate_id or "cand_1",
                hypothesis=hypothesis,
                triggered_by={"source": "agent", "prompt": user_prompt},
            )
            return collected, None

        return None, {
            "resolution_status": "EVIDENCE_UNAVAILABLE",
            "status_message": f"No evidence runs or candidate commits found for {ticker}.",
        }

    def __call__(self, state: EvidenceProposalState) -> dict[str, Any]:
        if state.get("resolution_status") == "NEEDS_CLARIFICATION":
            return {}

        experiment_id = state.get("experiment_id")
        user_prompt = state.get("user_prompt") or ""
        route = state.get("request")
        hypothesis = route.goal.objective if route and route.goal else (user_prompt or None)

        collector = (
            EvidenceCollector(db_manager=self._db_manager, vcs_service=self._vcs_service)
            if self._db_manager
            else None
        )

        if experiment_id:
            collected, error_res = self._collect_from_experiment(
                collector=collector,
                experiment_id=experiment_id,
                candidate_id=state.get("candidate_id"),
                hypothesis=hypothesis,
                user_prompt=user_prompt,
            )
        else:
            collected, error_res = self._collect_from_candidate(
                collector=collector,
                state=state,
                hypothesis=hypothesis,
                user_prompt=user_prompt,
            )

        if error_res:
            return error_res

        proposal = ProposalValidator.build_and_validate_proposal(collected)
        return {
            "collected_evidence": collected,
            "evidence_proposal": proposal,
            "resolution_status": "RESOLVED",
        }
