from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from api.interfaces.asset import Asset
from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
    ExecutionConfiguration,
)
from api.interfaces.backtest_run_spec import BacktestRunSpec
from src.backtest.analysis.metrics_calculator import BacktestMetricsCalculator
from src.backtest.data.backtest_data_source_resolver import BacktestDataSourceResolver
from src.backtest.domain.session import BacktestSession, generate_session_id
from src.backtest.runner.backtest_runner import BacktestRunner
from src.configuration.trading_config import TradingConfig
from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.execution_status import ExecutionStatus
from src.database.noop_database_manager import NoopDatabaseManager
from src.database.repositories.providers.postgres_backtest_repository import PostgresBacktestRepository
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.recorder.market_data_store import MarketDataStore
from src.server.services.dataset_service import DatasetService
from src.vcs.application.service import VCSService


class BacktestApplicationService(ApplicationLoggingMixin):
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
        self._calculator = BacktestMetricsCalculator()
        self._resolver = BacktestDataSourceResolver(
            market_data_store=self._market_data_store,
            dataset_service=self._dataset_service,
        )
        self._max_concurrent_runs = max(1, max_concurrent_runs)
        self._lease_duration_seconds = lease_duration_seconds
        self._abandoned_timeout_seconds = abandoned_timeout_seconds
        self._worker_id = worker_id or f"bt_worker_{uuid.uuid4().hex[:8]}"

        self._active_runs: set[str] = set()
        self._lock = threading.Lock()
        self._cancellation_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._stop_heartbeat_events: dict[str, threading.Event] = {}

    def start_backtest_run(self, spec: BacktestRunSpec) -> BacktestSession:
        vcs_ref = spec.configuration.vcs_commit_hash or "HEAD"
        raw_config = self._vcs_service.checkout(vcs_ref)
        trading_config = TradingConfig.model_validate(raw_config)

        asset_map: dict[str, Asset] = {a.ticker_symbol: a for a in trading_config.assets}
        if spec.ticker_symbol not in asset_map:
            raise ValueError(
                f"Asset '{spec.ticker_symbol}' not found in configuration snapshot ({vcs_ref}). "
                f"Available assets: {sorted(asset_map.keys())}"
            )

        session_id = spec.session_id or generate_session_id()
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresBacktestRepository)
            if repo.is_session_active(session_id) is True:
                raise ValueError(f"Backtest session '{session_id}' is already active.")

        source_type_val = spec.data_source.source_type.value
        if source_type_val in ("recorded_market_data", "market_data"):
            ds_type = BacktestDataSourceType.MARKET_DATA
        else:
            ds_type = BacktestDataSourceType.CSV

        ds_req = BacktestDataSourceRequest(
            source_type=ds_type,
            source_id=spec.data_source.dataset_id,
            path=spec.data_source.path,
        )

        exec_cfg = ExecutionConfiguration(
            latency_ms=spec.execution.latency_ms,
            slippage_ticks=spec.execution.slippage_ticks,
            fee_rate=spec.execution.fee_rate,
        )

        bt_request = BacktestRequest(
            ticker_symbol=spec.ticker_symbol,
            start_time=spec.period.start_time if spec.period else None,
            end_time=spec.period.end_time if spec.period else None,
            data_source=ds_req,
            initial_balance=spec.initial_balance,
            execution=exec_cfg,
        )

        session = BacktestSession(
            id=session_id,
            ticker_symbol=spec.ticker_symbol,
            request=bt_request,
            status=ExecutionStatus.QUEUED,
            created_at=datetime.now(timezone.utc),
        )

        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresBacktestRepository)
            repo.save_session(session)

        runner = BacktestRunner(
            db_manager=NoopDatabaseManager(),
            assets=asset_map,
            dynamic_quantity=trading_config.dynamic_quantity,
            data_source_resolver=self._resolver,
        )

        should_start_now = False
        with self._lock:
            if len(self._active_runs) < self._max_concurrent_runs:
                try:
                    with self._db_manager.get_unit_of_work() as uow:
                        repo = uow.get_repository(PostgresBacktestRepository)
                        acquired = repo.acquire_session(
                            session_id=session_id,
                            worker_id=self._worker_id,
                            lease_duration_seconds=self._lease_duration_seconds,
                        )
                    if acquired is True:
                        self._active_runs.add(session_id)
                        session.status = ExecutionStatus.RUNNING
                        session.started_at = datetime.now(timezone.utc)
                        should_start_now = True
                except Exception as exc:
                    self.app_logger.warning("Failed to immediately acquire backtest session %s: %s", session_id, exc)

        if should_start_now:
            thread = threading.Thread(
                target=self._execute_run,
                args=(runner, session),
                daemon=True,
            )
            self._threads[session_id] = thread
            thread.start()
        else:
            self._dispatch_next()

        return session

    def _dispatch_next(self) -> None:
        with self._lock:
            if len(self._active_runs) >= self._max_concurrent_runs:
                return

            try:
                with self._db_manager.get_unit_of_work() as uow:
                    repo = uow.get_repository(PostgresBacktestRepository)
                    session = repo.acquire_next_queued_session(
                        worker_id=self._worker_id,
                        lease_duration_seconds=self._lease_duration_seconds,
                    )
            except Exception as exc:
                self.app_logger.error("Error acquiring next queued backtest session: %s", exc, exc_info=True)
                return

            if not session or not session.id:
                return

            session_id = session.id
            if session_id in self._active_runs:
                return

            self._active_runs.add(session_id)

        try:
            raw_config = self._vcs_service.checkout("HEAD")
            trading_config = TradingConfig.model_validate(raw_config)
            asset_map = {a.ticker_symbol: a for a in trading_config.assets}

            runner = BacktestRunner(
                db_manager=NoopDatabaseManager(),
                assets=asset_map,
                dynamic_quantity=trading_config.dynamic_quantity,
                data_source_resolver=self._resolver,
            )

            thread = threading.Thread(
                target=self._execute_run,
                args=(runner, session),
                daemon=True,
            )
            self._threads[session_id] = thread
            thread.start()
        except Exception as exc:
            self.app_logger.error("Failed to spawn runner for backtest session %s: %s", session_id, exc, exc_info=True)
            with self._lock:
                self._active_runs.discard(session_id)
            try:
                with self._db_manager.get_unit_of_work() as uow:
                    repo = uow.get_repository(PostgresBacktestRepository)
                    repo.mark_failed(session_id, f"Failed to initialize runner: {exc}")
            except Exception:
                pass

    def _execute_run(self, runner: BacktestRunner, session: BacktestSession) -> None:
        stop_heartbeat = threading.Event()
        self._stop_heartbeat_events[session.id] = stop_heartbeat
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(session.id, stop_heartbeat),
            daemon=True,
        )
        heartbeat_thread.start()

        try:
            if self._is_session_cancelled(session.id):
                with self._db_manager.get_unit_of_work() as uow:
                    repo = uow.get_repository(PostgresBacktestRepository)
                    repo.mark_cancelled(session.id, reason="Run cancelled by user")
                return

            self.app_logger.info(f"Starting backtest simulation for session {session.id} ({session.ticker_symbol})")
            result = runner.run_session(session)
            metrics = self._calculator.calculate(result)
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresBacktestRepository)
                repo.mark_completed(session.id, result, metrics=metrics)
            session.complete(result)
            self.app_logger.info(f"Backtest simulation completed for session {session.id}")
        except InterruptedError as exc:
            self.app_logger.info(f"Backtest simulation cancelled for session {session.id}: {exc}")
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresBacktestRepository)
                repo.mark_cancelled(session.id, reason="Run cancelled by user")
            session.cancel()
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.error(f"Backtest simulation failed for session {session.id}: {exc}", exc_info=True)
            session.fail(str(exc))
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresBacktestRepository)
                repo.mark_failed(session.id, str(exc))
        finally:
            stop_heartbeat.set()
            with self._lock:
                self._active_runs.discard(session.id)
            self._dispatch_next()

    def _renew_heartbeat(self, session_id: str) -> None:
        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresBacktestRepository)
                repo.renew_lease(session_id, self._worker_id, self._lease_duration_seconds)
        except Exception as exc:
            self.app_logger.warning("Failed to renew heartbeat for backtest session %s: %s", session_id, exc)

    def _heartbeat_loop(self, session_id: str, stop_event: threading.Event) -> None:
        interval = max(1.0, float(self._lease_duration_seconds) / 3.0)
        while not stop_event.wait(timeout=interval):
            self._renew_heartbeat(session_id)

    def _is_session_cancelled(self, session_id: str) -> bool:
        evt = self._cancellation_events.get(session_id)
        if evt and evt.is_set():
            return True
        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresBacktestRepository)
                sess = repo.get_session(session_id)
                if sess and sess.status == ExecutionStatus.CANCELLED:
                    return True
        except Exception:
            pass
        return False

    def cancel_session(self, session_id: str, reason: Optional[str] = None) -> bool:
        if session_id in self._cancellation_events:
            self._cancellation_events[session_id].set()
        else:
            evt = threading.Event()
            evt.set()
            self._cancellation_events[session_id] = evt

        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresBacktestRepository)
            success = repo.mark_cancelled(session_id, reason=reason)

        with self._lock:
            self._active_runs.discard(session_id)

        self._dispatch_next()
        return success

    def recover_on_startup(self) -> list[str]:
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresBacktestRepository)
            recovered = repo.recover_abandoned_sessions(timeout_seconds=self._abandoned_timeout_seconds)
        self._dispatch_next()
        return recovered

    def wait_for_session(self, session_id: str, timeout: Optional[float] = None) -> None:
        thread = self._threads.get(session_id)
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
