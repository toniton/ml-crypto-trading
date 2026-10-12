from __future__ import annotations

import uuid
from typing import Any, Optional

from api.interfaces.experiment import (
    CandidateType,
    CreateExperimentRequest,
    ExperimentCandidate,
    ExperimentSpec,
    ExperimentStatus,
)
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_experiment_repository import (
    PostgresExperimentRepository,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.server.services.backtest_service import BacktestService
from src.vcs.application.service import VCSService
from src.vcs.domain.exceptions import CommitNotFoundError, InvalidReferenceError


class ExperimentApplicationService(ApplicationLoggingMixin):
    def __init__(
            self,
            db_manager: DatabaseManager,
            vcs_service: VCSService,
            backtest_service: BacktestService,
    ) -> None:
        self._db_manager = db_manager
        self._vcs_service = vcs_service
        self._backtest_service = backtest_service

    def create_experiment(self, req: CreateExperimentRequest) -> dict[str, Any]:
        base_commit = req.source_commit_hash
        if not base_commit:
            try:
                base_commit = self._vcs_service.resolve_commit_hash("refs/heads/main")
            except (CommitNotFoundError, InvalidReferenceError):
                base_commit = self._vcs_service.resolve_commit_hash("HEAD")

        branch_info = self._backtest_service.create_branch(
            name=f"exp-{req.name}",
            description=f"Experiment branch for {req.name}",
            source_commit_hash=base_commit,
            author="experiment-service",
        )
        branch_id = branch_info["branch_id"]

        candidates: list[ExperimentCandidate] = [
            ExperimentCandidate(
                candidate_id="cand_current",
                name="Current Configuration",
                candidate_type=CandidateType.CURRENT_CONFIG,
                strategy_weights={},
                description="Configuration as defined in experiment branch",
            )
        ]
        if req.control_policy.enable_equal_weight_baseline:
            candidates.append(
                ExperimentCandidate(
                    candidate_id="cand_equal_weight",
                    name="Equal-Weight Strategies",
                    candidate_type=CandidateType.EQUAL_WEIGHT,
                    strategy_weights={},
                    description="Equal weight baseline across all registered strategies",
                )
            )

        spec = ExperimentSpec(
            name=req.name,
            ticker_symbol=req.ticker_symbol,
            base_commit_hash=base_commit,
            branch_id=branch_id,
            test_selection=req.test_selection,
            data_source=req.data_source,
            period=req.period,
            windows=req.windows,
            initial_balance=req.initial_balance,
            execution=req.execution,
            control_policy=req.control_policy,
            candidates=candidates,
        )

        experiment_id = f"exp_{uuid.uuid4().hex[:12]}"
        spec_dict = spec.model_dump(mode="json")

        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            repo.save_experiment(
                experiment_id=experiment_id,
                name=req.name,
                ticker_symbol=req.ticker_symbol,
                branch_id=branch_id,
                base_commit_hash=base_commit,
                status=ExperimentStatus.DRAFT.value,
                spec=spec_dict,
                run_bindings=[],
                report=None,
            )

        self.app_logger.info(
            "Created experiment %s for %s on branch %s (base %s)",
            experiment_id,
            req.ticker_symbol,
            branch_id,
            base_commit[:8],
        )

        return {
            "experiment_id": experiment_id,
            "id": experiment_id,
            "name": req.name,
            "ticker_symbol": req.ticker_symbol,
            "branch_id": branch_id,
            "base_commit_hash": base_commit,
            "status": ExperimentStatus.DRAFT.value,
            "spec": spec_dict,
            "run_bindings": [],
            "report": None,
        }

    def get_experiment(self, experiment_id: str) -> Optional[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            return repo.get_experiment(experiment_id)

    def list_experiments(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            return repo.list_experiments(limit=limit, offset=offset)

    def update_experiment_spec(self, experiment_id: str, spec: ExperimentSpec) -> dict[str, Any]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            existing = repo.get_experiment(experiment_id)
            if not existing:
                raise ValueError(f"Experiment '{experiment_id}' not found.")
            if existing["status"] != ExperimentStatus.DRAFT.value:
                raise ValueError(f"Cannot update experiment '{experiment_id}' in status '{existing['status']}'.")

            spec_dict = spec.model_dump(mode="json")
            repo.save_experiment(
                experiment_id=experiment_id,
                name=spec.name,
                ticker_symbol=spec.ticker_symbol,
                branch_id=existing["branch_id"],
                base_commit_hash=existing["base_commit_hash"],
                status=existing["status"],
                spec=spec_dict,
                run_bindings=existing.get("run_bindings", []),
                report=existing.get("report"),
            )
            return repo.get_experiment(experiment_id) or {}

    def delete_experiment(self, experiment_id: str) -> bool:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresExperimentRepository)
            existing = repo.get_experiment(experiment_id)
            if not existing:
                return False

            branch_id = existing.get("branch_id")
            if branch_id:
                try:
                    self._backtest_service.delete_branch(branch_id)
                except Exception as exc:  # pylint: disable=broad-except
                    self.app_logger.warning(
                        "Could not delete branch %s for experiment %s: %s",
                        branch_id,
                        experiment_id,
                        exc,
                    )

            return repo.delete_experiment(experiment_id)
