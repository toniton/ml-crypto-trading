from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
    ExecutionConfiguration,
)
from src.backtest.analysis.metrics_calculator import BacktestMetricsCalculator
from src.backtest.domain.metrics import BacktestSummary
from src.backtest.domain.result import BacktestResult
from src.backtest.domain.session import BacktestSession
from src.backtest.runner.backtest_runner import BacktestRunner
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_backtest_repository import PostgresBacktestRepository
from src.logging.agent_logging_mixin import AgentLoggingMixin


class BacktestService(AgentLoggingMixin):
    """Agent-facing application boundary for running backtests.

    The service deals exclusively in requests: it describes *what* to backtest
    and delegates data acquisition to the runner (which resolves the request's
    ``data_source``). It never acquires market data itself.
    """

    def __init__(
            self,
            runner: BacktestRunner,
            data_source_request: BacktestDataSourceRequest,
            initial_balance: Decimal,
            execution: ExecutionConfiguration,
            db_manager: DatabaseManager,
    ):
        self._runner = runner
        self._data_source_request = data_source_request
        self._initial_balance = initial_balance
        self._execution = execution
        self._db_manager = db_manager
        self._calculator = BacktestMetricsCalculator()
        self._sessions: dict[str, BacktestSession] = {}
        self._results: dict[str, BacktestResult] = {}

    def create(self, request: BacktestRequest) -> BacktestSession:
        session = BacktestSession(ticker_symbol=request.ticker_symbol, request=request)
        self._sessions[session.id] = session
        return session

    def run(self, request: BacktestRequest) -> BacktestResult:
        """Run a backtest for the given request and return its result.

        This is the canonical application entry point: the request is the complete
        description of the backtest, and data acquisition is delegated to the
        runner (which resolves the request's ``data_source``).
        """

        session = self.create(request)
        self.agent_logger.info(f"Running backtest for {request.ticker_symbol}")
        result = self._runner.run_session(session)
        self._sessions[session.id] = session
        self._results[session.id] = result
        self._persist_run(session, result)
        return result

    def _persist_run(self, session: BacktestSession, result: BacktestResult) -> None:
        if self._db_manager is None:
            return
        try:
            metrics = self._calculator.calculate(result)
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresBacktestRepository)
                repo.save_session(session)
                repo.save_result(result, metrics=metrics)
            self.agent_logger.info(f"Persisted backtest result for session {session.id} to database")
        except Exception as exc:  # pylint: disable=broad-except
            self.agent_logger.warning(f"Failed to persist backtest result to database: {exc}")

    def get(self, session_id: str) -> BacktestSession:
        if session_id in self._sessions:
            return self._sessions[session_id]
        if self._db_manager is not None:
            try:
                with self._db_manager.get_unit_of_work() as uow:
                    repo = uow.get_repository(PostgresBacktestRepository)
                    session = repo.get_session(session_id)
                    if session is not None:
                        self._sessions[session_id] = session
                        return session
            except Exception as exc:  # pylint: disable=broad-except
                self.agent_logger.warning(f"Failed to load session {session_id} from database: {exc}")
        raise KeyError(f"Backtest session '{session_id}' not found.")

    def result(self, session_id: str) -> BacktestResult:
        if session_id in self._results:
            return self._results[session_id]
        if self._db_manager is not None:
            try:
                with self._db_manager.get_unit_of_work() as uow:
                    repo = uow.get_repository(PostgresBacktestRepository)
                    res = repo.get_result(session_id)
                    if res is not None:
                        self._results[session_id] = res
                        return res
            except Exception as exc:  # pylint: disable=broad-except
                self.agent_logger.warning(f"Failed to load result for session {session_id} from database: {exc}")
        raise KeyError(f"Backtest result for session '{session_id}' not found.")

    def list_sessions(self, limit: int = 50) -> list[BacktestSession]:
        if self._db_manager is not None:
            try:
                with self._db_manager.get_unit_of_work() as uow:
                    repo = uow.get_repository(PostgresBacktestRepository)
                    db_sessions = repo.list_sessions(limit=limit)
                    if db_sessions:
                        return db_sessions
            except Exception as exc:  # pylint: disable=broad-except
                self.agent_logger.warning(f"Failed to list backtest sessions from database: {exc}")
        return list(self._sessions.values())[:limit]

    def summary(self, session_id: str) -> BacktestSummary:
        session = self.get(session_id)
        metrics = self._calculator.calculate(self.result(session_id))
        return self._calculator.summarize(session, metrics)

    def run_asset(
            self,
            ticker_symbol: str,
            source_type: BacktestDataSourceType | None = None,
    ) -> BacktestSummary:
        """Run a backtest for a single asset and return its compact summary."""

        result = self.run(self.build_request(ticker_symbol, source_type))
        return self.summary(result.session_id)

    def build_request(
            self,
            ticker_symbol: str,
            source_type: BacktestDataSourceType | None = None,
            start_time: datetime | None = None,
            end_time: datetime | None = None,
            execution: ExecutionConfiguration | None = None,
    ) -> BacktestRequest:
        return BacktestRequest(
            ticker_symbol=ticker_symbol,
            start_time=start_time,
            end_time=end_time,
            data_source=self._data_source_request_for(source_type),
            initial_balance=self._initial_balance,
            execution=execution or self._execution,
        )

    def _data_source_request_for(
            self,
            source_type: BacktestDataSourceType | None,
    ) -> BacktestDataSourceRequest:
        if source_type is None or source_type == BacktestDataSourceType.CSV:
            return self._data_source_request
        if source_type == BacktestDataSourceType.MARKET_DATA:
            return BacktestDataSourceRequest(
                source_type=BacktestDataSourceType.MARKET_DATA
            )
        raise ValueError(f"Unsupported data source type: {source_type}")
