from __future__ import annotations

from typing import Any, Optional

from src.agent.evidence_proposal.state import EvidenceProposalState
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_experiment_repository import (
    PostgresExperimentRepository,
)
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
            or "BTC_USD"
        )
        experiment_id = (
            (refs.experiment_id if refs and refs.experiment_id else None)
            or state.get("experiment_id")
        )
        candidate_id = (
            (refs.candidate_id if refs and refs.candidate_id else None)
            or state.get("candidate_id")
        )
        commit_hash = (
            (refs.commit_hash if refs and refs.commit_hash else None)
            or state.get("baseline_commit")
        )

        if not experiment_id and self._db_manager:
            experiment_id, candidate_id = self._find_latest_experiment(ticker, candidate_id)

        baseline_commit = commit_hash or self._resolve_head_commit()

        return {
            "ticker_symbol": ticker,
            "experiment_id": experiment_id,
            "candidate_id": candidate_id,
            "baseline_commit": baseline_commit,
        }

    def _find_latest_experiment(
            self,
            ticker: str,
            candidate_id: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        if not self._db_manager:
            return None, candidate_id
        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresExperimentRepository)
                experiments = repo.list_experiments(limit=10)
                for exp in experiments:
                    if exp.get("ticker_symbol") == ticker:
                        exp_id = exp.get("experiment_id") or exp.get("id")
                        if not candidate_id:
                            candidate_id = self._pick_non_baseline_candidate(exp)
                        return exp_id, candidate_id
        except Exception:  # pylint: disable=broad-except
            pass
        return None, candidate_id

    @staticmethod
    def _pick_non_baseline_candidate(exp: dict[str, Any]) -> Optional[str]:
        candidates = exp.get("candidates") or []
        for cand in candidates:
            cid = cand.get("candidate_id")
            if cid and cid != "cand_current":
                return cid
        return candidates[0].get("candidate_id") if candidates else None

    def _resolve_head_commit(self) -> str:
        if self._vcs_service:
            try:
                return self._vcs_service.resolve_commit_hash("HEAD")
            except Exception:  # pylint: disable=broad-except
                pass
        return "HEAD"
