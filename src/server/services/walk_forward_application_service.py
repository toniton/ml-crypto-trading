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
            max_concurrent_runs: int = 2,
            lease_duration_seconds: int = 60,
            abandoned_timeout_seconds: int = 120,
            worker_id: Optional[str] = None,
    ) -> None:
        self._db_manager = db_manager
        self._vcs_service = vcs_service
        self._market_data_store = market_data_store
        self._dataset_service = dataset_service
        self._resolver = SimulationDataSourceResolver(
            market_data_store=self._market_data_store,
            dataset_service=self._dataset_service,
        )
        self._max_concurrent_runs = max(1, max_concurrent_runs)
        self._lease_duration_seconds = lease_duration_seconds
        self._abandoned_timeout_seconds = abandoned_timeout_seconds
        self._worker_id = worker_id or f"wf_worker_{uuid.uuid4().hex[:8]}"

        self._active_runs: set[str] = set()
        self._lock = threading.Lock()
        self._cancellation_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._stop_heartbeat_events: dict[str, threading.Event] = {}

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

        run_id = spec.run_id or f"wf_{uuid.uuid4().hex[:12]}"
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresWalkForwardRepository)
            if repo.is_run_active(run_id) is True:
                raise ValueError(f"Walk-forward run '{run_id}' is already active.")

        spec = spec.model_copy(deep=True)
        spec.configuration.vcs_commit_hash = resolved_commit_hash
        if not spec.software_version:
            spec.software_version = "1.0.0"

        spec_dict = spec.model_dump(mode="json")

        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresWalkForwardRepository)
                repo.save_run(
                    run_id=run_id,
                    ticker_symbol=spec.ticker_symbol,
                    status="QUEUED",
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

        should_start_now = False
        with self._lock:
            if len(self._active_runs) < self._max_concurrent_runs:
                try:
                    with self._db_manager.get_unit_of_work() as uow:
                        repo = uow.get_repository(PostgresWalkForwardRepository)
                        acquired = repo.acquire_run(
                            run_id=run_id,
                            worker_id=self._worker_id,
                            lease_duration_seconds=self._lease_duration_seconds,
                        )
                    if acquired is True:
                        self._active_runs.add(run_id)
                        should_start_now = True
                except Exception as exc:
                    self.app_logger.warning("Failed to immediately acquire run %s: %s", run_id, exc)

        if should_start_now:
            thread = threading.Thread(
                target=self._execute_run,
                args=(runner, spec, run_id),
                daemon=True,
            )
            self._threads[run_id] = thread
            thread.start()
        else:
            self._dispatch_next()

        return {
            "run_id": run_id,
            "status": "RUNNING" if should_start_now else "QUEUED",
            "ticker_symbol": spec.ticker_symbol,
            "spec": spec_dict,
            "vcs_commit_hash": resolved_commit_hash,
            "software_version": spec.software_version,
        }

    def _dispatch_next(self) -> None:
        with self._lock:
            if len(self._active_runs) >= self._max_concurrent_runs:
                return

            try:
                with self._db_manager.get_unit_of_work() as uow:
                    repo = uow.get_repository(PostgresWalkForwardRepository)
                    acquired = repo.acquire_next_queued_run(
                        worker_id=self._worker_id,
                        lease_duration_seconds=self._lease_duration_seconds,
                    )
            except Exception as exc:
                self.app_logger.error("Error acquiring next queued walk-forward run: %s", exc, exc_info=True)
                return

            if not isinstance(acquired, dict) or "run_id" not in acquired or "spec" not in acquired:
                return

            run_id = str(acquired["run_id"])
            if run_id in self._active_runs:
                return

            self._active_runs.add(run_id)

        try:
            raw_spec = acquired["spec"]
            if isinstance(raw_spec, WalkForwardRunSpec):
                spec = raw_spec
            elif isinstance(raw_spec, dict):
                spec = WalkForwardRunSpec.model_validate(raw_spec)
            else:
                raise ValueError(f"Invalid spec format in acquired run {run_id}")

            vcs_ref = spec.configuration.vcs_commit_hash or "HEAD"
            if vcs_ref in ("HEAD", "main", "master") or vcs_ref.startswith("refs/"):
                resolved_commit = self._vcs_service.resolve_commit_hash(vcs_ref)
            else:
                resolved_commit = vcs_ref
            raw_config = self._vcs_service.checkout(resolved_commit)
            trading_config = TradingConfig.model_validate(raw_config)
            asset_map = {a.ticker_symbol: a for a in trading_config.assets}

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
        except Exception as exc:
            self.app_logger.error("Failed to spawn runner for run %s: %s", run_id, exc, exc_info=True)
            with self._lock:
                self._active_runs.discard(run_id)
            try:
                with self._db_manager.get_unit_of_work() as uow:
                    repo = uow.get_repository(PostgresWalkForwardRepository)
                    repo.mark_failed(run_id, f"Failed to initialize runner: {exc}")
            except Exception:
                pass

    def _execute_run(self, runner: WalkForwardRunner, spec: WalkForwardRunSpec, run_id: str) -> None:
        stop_heartbeat = threading.Event()
        self._stop_heartbeat_events[run_id] = stop_heartbeat
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(run_id, stop_heartbeat),
            daemon=True,
        )
        heartbeat_thread.start()

        try:
            self.app_logger.info("Executing walk-forward run %s for %s", run_id, spec.ticker_symbol)
            summary = runner.run(
                spec,
                run_id=run_id,
                on_fold_complete=lambda _: self._renew_heartbeat(run_id),
                is_cancelled=lambda: self._is_run_cancelled(run_id),
            )
            summary_dict = summary.model_dump(mode="json")
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresWalkForwardRepository)
                repo.update_run_summary(run_id=run_id, status="COMPLETED", summary=summary_dict)
            self.app_logger.info("Walk-forward run %s successfully completed", run_id)
        except InterruptedError as exc:
            self.app_logger.info("Walk-forward run %s cancelled: %s", run_id, exc)
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresWalkForwardRepository)
                repo.mark_cancelled(run_id, reason="Run cancelled by user")
        except Exception as exc:
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
                                or spec.data_source.source_type.value
                            ),
                            "execution_assumptions": spec.execution.model_dump(mode="json"),
                            "strategy_weights": {
                                "candidate": spec.candidate_weights,
                                "baseline": spec.baseline_weights,
                            } if (spec.candidate_weights or spec.baseline_weights) else None,
                            "candidate_weights": spec.candidate_weights,
                            "baseline_weights": spec.baseline_weights,
                            "software_version": spec.software_version or "1.0.0",
                        },
                    )
            except Exception:
                pass
        finally:
            stop_heartbeat.set()
            with self._lock:
                self._active_runs.discard(run_id)
            self._dispatch_next()

    def _renew_heartbeat(self, run_id: str) -> None:
        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresWalkForwardRepository)
                repo.renew_lease(run_id, self._worker_id, self._lease_duration_seconds)
        except Exception as exc:
            self.app_logger.warning("Failed to renew heartbeat for run %s: %s", run_id, exc)

    def _heartbeat_loop(self, run_id: str, stop_event: threading.Event) -> None:
        interval = max(1.0, float(self._lease_duration_seconds) / 3.0)
        while not stop_event.wait(timeout=interval):
            self._renew_heartbeat(run_id)

    def _is_run_cancelled(self, run_id: str) -> bool:
        evt = self._cancellation_events.get(run_id)
        if evt and evt.is_set():
            return True
        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresWalkForwardRepository)
                run = repo.get_run(run_id)
                if run and run.get("status") == "CANCELLED":
                    return True
        except Exception:
            pass
        return False

    def cancel_run(self, run_id: str, reason: Optional[str] = None) -> bool:
        if run_id in self._cancellation_events:
            self._cancellation_events[run_id].set()
        else:
            evt = threading.Event()
            evt.set()
            self._cancellation_events[run_id] = evt

        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresWalkForwardRepository)
            success = repo.mark_cancelled(run_id, reason=reason)

        with self._lock:
            self._active_runs.discard(run_id)

        self._dispatch_next()
        return success

    def recover_on_startup(self) -> list[str]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresWalkForwardRepository)
            recovered = repo.recover_abandoned_runs(timeout_seconds=self._abandoned_timeout_seconds)
        self._dispatch_next()
        return recovered

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
