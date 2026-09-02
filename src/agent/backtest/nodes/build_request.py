from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestRequest,
    ExecutionConfiguration,
)
from src.agent.backtest.models import BacktestAgentRequest, BacktestTimeRange
from src.agent.backtest.state import BacktestAgentState


class BuildBacktestRequestNode:
    def __call__(self, state: BacktestAgentState) -> dict:
        agent_request = state["backtest_request"]
        route = state.get("request")
        ticker = agent_request.ticker_symbol or (
            route.goal.target_asset if route and route.goal else None
        )
        if not ticker:
            return {"resolved_request": None}

        start, end = self._resolve_time(agent_request.time_range)
        execution = self._resolve_execution(agent_request)
        resolved = BacktestRequest(
            ticker_symbol=ticker,
            start_time=start,
            end_time=end,
            data_source=BacktestDataSourceRequest(source_type=agent_request.data_source),
            execution=execution if execution is not None else ExecutionConfiguration(),
        )
        return {"resolved_request": resolved}


    @staticmethod
    def _resolve_execution(agent_request: BacktestAgentRequest) -> ExecutionConfiguration | None:
        if (
                agent_request.fee_rate is None
                or agent_request.slippage_ticks is None
                or agent_request.latency_ms is None
        ):
            return None
        return ExecutionConfiguration(
            latency_ms=agent_request.latency_ms,
            slippage_ticks=agent_request.slippage_ticks,
            fee_rate=Decimal(str(agent_request.fee_rate)),
        )

    @staticmethod
    def _resolve_time(time_range: BacktestTimeRange) -> tuple[datetime | None, datetime | None]:
        if time_range.mode == "absolute":
            return time_range.start_time, time_range.end_time
        end = datetime.now(timezone.utc)
        duration = time_range.duration_seconds or 0
        start = end - timedelta(seconds=duration)
        return start, end
