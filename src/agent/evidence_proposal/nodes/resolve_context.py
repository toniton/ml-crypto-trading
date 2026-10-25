from __future__ import annotations

from typing import Any, Optional

from src.agent.evidence_proposal.state import EvidenceProposalState
from src.core.interfaces.database_manager import DatabaseManager
from src.vcs.application.service import VCSService


class ResolveContextNode:
    def __init__(
            self,
            db_manager: Optional[DatabaseManager] = None,
            vcs_service: Optional[VCSService] = None,
    ):
        self._db_manager = db_manager
        self._vcs_service = vcs_service

    def __call__(self, state: EvidenceProposalState) -> dict[str, Any]:
        route = state.get("request")
        refs = route.references if route and route.references else None
        goal = route.goal if route else None

        ticker = (
                (refs.asset if refs and refs.asset else None)
                or (goal.target_asset if goal and goal.target_asset else None)
                or state.get("ticker_symbol")
        )
        if not ticker:
            return {
                "resolution_status": "NEEDS_CLARIFICATION",
                "status_message": (
                    "Please specify which asset (e.g. BTC_USD) you would like to evaluate for an "
                    "evidence-based proposal."
                ),
                "missing_fields": ["ticker_symbol"],
            }

        experiment_id = (
                (refs.experiment_id if refs and refs.experiment_id else None)
                or state.get("experiment_id")
        )
        candidate_id = (
                (refs.candidate_id if refs and refs.candidate_id else None)
                or state.get("candidate_id")
        )
        candidate_commit = (
            (refs.commit_hash if refs and refs.commit_hash else None)
            or state.get("candidate_commit")
        )
        baseline_commit = state.get("baseline_commit") or self._resolve_head_commit()

        if not experiment_id and not candidate_commit and not candidate_id:
            return {
                "ticker_symbol": ticker,
                "baseline_commit": baseline_commit,
                "resolution_status": "NEEDS_CLARIFICATION",
                "status_message": (
                    f"Please specify the experiment ID (e.g. 'exp_...') or candidate commit to evaluate "
                    f"against baseline for {ticker}."
                ),
                "missing_fields": ["experiment_id", "candidate_commit"],
            }

        return {
            "ticker_symbol": ticker,
            "experiment_id": experiment_id,
            "candidate_id": candidate_id,
            "candidate_commit": candidate_commit,
            "baseline_commit": baseline_commit,
            "resolution_status": "RESOLVED",
        }

    def _resolve_head_commit(self) -> str:
        if self._vcs_service:
            try:
                return self._vcs_service.resolve_commit_hash("HEAD")
            except Exception:  # pylint: disable=broad-except
                pass
        return "HEAD"
