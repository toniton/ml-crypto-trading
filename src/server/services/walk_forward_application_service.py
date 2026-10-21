from __future__ import annotations

import threading
import uuid
from typing import Any, Optional

from api.interfaces.asset import Asset
from api.interfaces.walk_forward import WalkForwardRunSpec
from src.configuration.trading_config import TradingConfig
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_walk_forward_repository import (
    PostgresWalkForwardRepository,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.backtest.data.backtest_data_source_resolver import (
    SimulationDataSourceResolver,
)
from src.recorder.market_data_store import MarketDataStore
from src.server.services.dataset_service import DatasetService
from src.vcs.application.service import VCSService
from src.walk_forward.runner.walk_forward_runner import WalkForwardRunner


class WalkForwardApplicationService(ApplicationLoggingMixin):
    def __init__(
            self,
            db_manager: DatabaseManager,
            vcs_service: VCSService,
            market_data_store: MarketDataStore,
            dataset_service: DatasetService,
    ) -> None:
        self._db_manager = db_manager
        self._vcs_service = vcs_service
        self._market_data_store = market_data_store
        self._dataset_service = dataset_service
        self._resolver = SimulationDataSourceResolver(
            market_data_store=self._market_data_store,
            dataset_service=self._dataset_service,
        )
        self._threads: dict[str, threading.Thread] = {}

    def start_run(self, spec: WalkForwardRunSpec) -> dict[str, Any]:
        vcs_ref = spec.configuration.vcs_commit_hash or "HEAD"
        resolved_commit_hash = self._vcs_service.resolve_commit_hash(vcs_ref)
        raw_config = self._vcs_service.checkout(resolved_commit_hash)
        trading_config = TradingConfig.model_validate(raw_config)

        asset_map: dict[str, Asset] = {a.ticker_symbol: a for a in trading_config.assets}
        if spec.ticker_symbol not in asset_map:
            raise ValueError(
                f"Asset '{spec.ticker_symbol}' not found in configuration snapshot ({resolved_commit_hash}). "
                f"Available assets: {sorted(asset_map.keys())}"
            )

        run_id = f"wf_{uuid.uuid4().hex[:12]}"
        spec = spec.model_copy(deep=True)
        spec.configuration.vcs_commit_hash = resolved_commit_hash
        if not getattr(spec, "software_version", None):
            spec.software_version = "1.0.0"

        spec_dict = spec.model_dump(mode="json")

        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresWalkForwardRepository)
                repo.save_run(
                    run_id=run_id,
                    ticker_symbol=spec.ticker_symbol,
                    status="RUNNING",
                    spec=spec_dict,
                )
        except Exception as exc:
            self.app_logger.error("Failed to persist initial walk-forward run record: %s", exc, exc_info=True)
            raise RuntimeError(f"Failed to persist initial walk-forward run record: {exc}") from exc

        runner = WalkForwardRunner(
            db_manager=self._db_manager,
            assets=asset_map,
            dynamic_quantity=trading_config.dynamic_quantity,
            data_source_resolver=self._resolver,
        )

        thread = threading.Thread(
            target=self._execute_run,
            args=(runner, spec, run_id),
            daemon=True,
        )
        self._threads[run_id] = thread
        thread.start()

        return {
            "run_id": run_id,
            "status": "RUNNING",
            "ticker_symbol": spec.ticker_symbol,
            "spec": spec_dict,
            "vcs_commit_hash": resolved_commit_hash,
            "software_version": spec.software_version,
        }

    def _execute_run(self, runner: WalkForwardRunner, spec: WalkForwardRunSpec, run_id: str) -> None:
        try:
            self.app_logger.info("Executing walk-forward run %s for %s", run_id, spec.ticker_symbol)
            summary = runner.run(spec, run_id=run_id)
            summary_dict = summary.model_dump(mode="json")
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresWalkForwardRepository)
                repo.update_run_summary(run_id=run_id, status="COMPLETED", summary=summary_dict)
            self.app_logger.info("Walk-forward run %s successfully completed", run_id)
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.error("Walk-forward run %s failed: %s", run_id, exc, exc_info=True)
            try:
                with self._db_manager.get_unit_of_work() as uow:
                    repo = uow.get_repository(PostgresWalkForwardRepository)
                    repo.update_run_summary(
                        run_id=run_id,
                        status="FAILED",
                        summary={
                            "error": str(exc),
                            "error_message": str(exc),
                            "vcs_commit_hash": spec.configuration.vcs_commit_hash,
                            "dataset_identity": (
                                spec.data_source.dataset_id
                                or spec.data_source.path
                                or (
                                    spec.data_source.source_type.value
                                    if hasattr(spec.data_source.source_type, "value")
                                    else str(spec.data_source.source_type)
                                )
                            ),
                            "execution_assumptions": spec.execution.model_dump(mode="json"),
                            "strategy_weights": {
                                "candidate": spec.candidate_weights,
                                "baseline": spec.baseline_weights,
                            } if (spec.candidate_weights or spec.baseline_weights) else None,
                            "candidate_weights": spec.candidate_weights,
                            "baseline_weights": spec.baseline_weights,
                            "software_version": getattr(spec, "software_version", "1.0.0"),
                        },
                    )
            except Exception:  # pylint: disable=broad-except
                pass

    def wait_for_run(self, run_id: str, timeout: Optional[float] = None) -> None:
        thread = self._threads.get(run_id)
        if thread and thread.is_alive():
            thread.join(timeout=timeout)

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresWalkForwardRepository)
            return repo.get_run(run_id)

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresWalkForwardRepository)
            return repo.list_runs(limit)
