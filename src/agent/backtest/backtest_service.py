from __future__ import annotations

from decimal import Decimal

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestRequest,
    ExecutionConfiguration,
)
from src.backtest.analysis.metrics_calculator import BacktestMetricsCalculator
from src.backtest.domain.metrics import BacktestSummary
from src.backtest.domain.result import BacktestResult
from src.backtest.domain.session import BacktestSession
from src.backtest.runner.backtest_runner import BacktestRunner
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
    ):
        self._runner = runner
        self._data_source_request = data_source_request
        self._initial_balance = initial_balance
        self._execution = execution
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
        return result

    def get(self, session_id: str) -> BacktestSession:
        return self._sessions[session_id]

    def result(self, session_id: str) -> BacktestResult:
        return self._results[session_id]

    def summary(self, session_id: str) -> BacktestSummary:
        session = self.get(session_id)
        metrics = self._calculator.calculate(self.result(session_id))
        return self._calculator.summarize(session, metrics)

    def run_asset(self, ticker_symbol: str) -> BacktestSummary:
        """Run a backtest for a single asset and return its compact summary."""

        result = self.run(self.build_request(ticker_symbol))
        return self.summary(result.session_id)

    def build_request(self, ticker_symbol: str) -> BacktestRequest:
        return BacktestRequest(
            ticker_symbol=ticker_symbol,
            data_source=self._data_source_request,
            initial_balance=self._initial_balance,
            execution=self._execution,
        )
