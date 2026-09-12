from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

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
from src.backtest.domain.session import BacktestSession, BacktestSessionStatus
from src.backtest.runner.backtest_runner import BacktestRunner
from src.configuration.trading_config import TradingConfig
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_backtest_repository import PostgresBacktestRepository
from src.recorder.market_data_store import MarketDataStore
from src.server.services.dataset_service import DatasetService
from src.vcs.application.service import VCSService

logger = logging.getLogger(__name__)


class BacktestApplicationService:
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
        self._calculator = BacktestMetricsCalculator()
        self._resolver = BacktestDataSourceResolver(
            market_data_store=self._market_data_store,
            dataset_service=self._dataset_service,
        )

    def start_backtest_run(self, spec: BacktestRunSpec) -> BacktestSession:
        vcs_ref = spec.configuration.vcs_commit_hash or "HEAD"
        raw_config = self._vcs_service.checkout(vcs_ref)
        trading_config = TradingConfig.model_validate(raw_config)

        # Match ticker in config
        asset_map: dict[str, Asset] = {a.ticker_symbol: a for a in trading_config.assets}
        if spec.ticker_symbol not in asset_map:
            raise ValueError(
                f"Asset '{spec.ticker_symbol}' not found in configuration snapshot ({vcs_ref}). "
                f"Available assets: {sorted(asset_map.keys())}"
            )

        # Map data source
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
            ticker_symbol=spec.ticker_symbol,
            request=bt_request,
            status=BacktestSessionStatus.RUNNING,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
        )

        # Persist session in state RUNNING
        with self._db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresBacktestRepository)
            repo.save_session(session)

        # Spawn background execution
        runner = BacktestRunner(
            db_manager=self._db_manager,
            assets=asset_map,
            dynamic_quantity=trading_config.dynamic_quantity,
            data_source_resolver=self._resolver,
        )

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, self._execute_run, runner, session)

        return session

    def _execute_run(self, runner: BacktestRunner, session: BacktestSession) -> None:
        try:
            logger.info(f"Starting backtest simulation for session {session.id} ({session.ticker_symbol})")
            result = runner.run_session(session)
            metrics = self._calculator.calculate(result)
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresBacktestRepository)
                repo.save_session(session)
                repo.save_result(result, metrics=metrics)
            logger.info(f"Backtest simulation completed for session {session.id}")
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"Backtest simulation failed for session {session.id}: {exc}", exc_info=True)
            session.fail(str(exc))
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresBacktestRepository)
                repo.save_session(session)
