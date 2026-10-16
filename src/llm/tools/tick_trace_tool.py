from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.activity.asset_activity_tracker import AssetActivityTracker
from src.trading.decision.decision_manager import DecisionManager


@dataclass
class ScheduleTickTrace:  # pylint: disable=too-many-instance-attributes
    tick_id: str
    ticker_symbol: str
    exchange: str
    timestamp: float
    schedule: str = "EVERY_MINUTE"
    market_data_fresh: bool = True
    candle_timestamp: Optional[float] = None
    candle_age_seconds: float = 0.0
    close_price: Optional[str] = None
    strategy_evaluations: dict[str, dict[str, Any]] = field(default_factory=dict)
    consensus_quorum: bool = False
    vote_ratio: float = 0.0
    quorum_threshold: float = 0.6
    winning_strategy: Optional[str] = None
    risk_passed: Optional[bool] = None
    guard_evaluations: list[dict[str, Any]] = field(default_factory=list)
    decision_id: Optional[str] = None
    order_id: Optional[str] = None
    order_status: Optional[str] = None
    submitted_at: Optional[float] = None
    filled_at: Optional[float] = None
    execution_latency_ms: Optional[float] = None
    reconciled: Optional[bool] = None
    reconciliation_note: Optional[str] = None
    terminal_stage: str = "COMPLETED"
    no_order_reason: Optional[str] = None


class ScheduleTickTracer:
    def __init__(self, max_traces: int = 500):
        self._max_traces = max_traces
        self._traces: list[ScheduleTickTrace] = []

    def record(self, trace: ScheduleTickTrace) -> None:
        self._traces.append(trace)
        if len(self._traces) > self._max_traces:
            del self._traces[: len(self._traces) - self._max_traces]

    def get(self, tick_id: str) -> Optional[ScheduleTickTrace]:
        for t in reversed(self._traces):
            if t.tick_id == tick_id:
                return t
        return None

    def list_by_symbol(self, ticker_symbol: Optional[str] = None, limit: int = 10) -> list[ScheduleTickTrace]:
        items = list(reversed(self._traces))
        if ticker_symbol:
            target = ticker_symbol.strip().upper()
            items = [t for t in items if t.ticker_symbol.upper() == target]
        return items[:limit]


class TickTraceInput(BaseModel):
    tick_id: Optional[str] = Field(
        default=None,
        description="Specific schedule tick ID (e.g. 'tick-1901') to inspect end-to-end.",
    )
    ticker_symbol: Optional[str] = Field(
        default=None,
        description="Ticker symbol (e.g. 'BTC_USD') to inspect recent schedule ticks and no-order reasons.",
    )
    limit: int = Field(
        default=5,
        description="Maximum number of recent tick traces to return.",
    )


class TickTraceTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "inspect_schedule_tick_trace"
    description: str = (
        "Inspects end-to-end schedule tick traces from scheduler tick through market-data freshness, "
        "strategy evaluations, consensus quorum, risk/guard checks, order submission, fill execution, "
        "and reconciliation—including ticks that produced no order."
    )
    args_schema: Type[BaseModel] = TickTraceInput
    tick_tracer: Optional[ScheduleTickTracer] = None
    activity_tracker: Optional[AssetActivityTracker] = None
    decision_manager: Optional[DecisionManager] = None

    def __init__(
            self,
            tick_tracer: Optional[ScheduleTickTracer] = None,
            activity_tracker: Optional[AssetActivityTracker] = None,
            decision_manager: Optional[DecisionManager] = None,
    ):
        super().__init__(
            tick_tracer=tick_tracer,
            activity_tracker=activity_tracker,
            decision_manager=decision_manager,
        )

    def _run(  # pylint: disable=arguments-differ
            self,
            tick_id: Optional[str] = None,
            ticker_symbol: Optional[str] = None,
            limit: int = 5,
    ) -> str:
        if tick_id and self.tick_tracer:
            trace = self.tick_tracer.get(tick_id.strip())
            if not trace:
                return f"No schedule tick trace found for ID '{tick_id}'."
            return self._format_trace_detail(trace)

        traces = self.tick_tracer.list_by_symbol(ticker_symbol, limit=limit) if self.tick_tracer else []
        lines: list[str] = []

        if ticker_symbol and self.activity_tracker is not None:
            state = self.activity_tracker.state_for(ticker_symbol.strip())
            if state is not None:
                lines.append(
                    f"=== Live Activity Stage Summary ({ticker_symbol.strip()}) ===\n"
                    f"  Last Market Data:         {self._fmt_ts(state.last_market_data_at)}\n"
                    f"  Last Strategy Evaluation: {self._fmt_ts(state.last_evaluation_at)}\n"
                    f"  Last Signal Generated:    {self._fmt_ts(state.last_signal_at)}\n"
                    f"  Last Order Submitted:     {self._fmt_ts(state.last_order_at)}\n"
                    f"  Last Order Executed:      {self._fmt_ts(state.last_execution_at)}"
                )

        if traces:
            lines.append(f"=== Schedule Tick Traces ({len(traces)} found) ===")
            for t in traces:
                lines.append(self._format_trace_detail(t))
            return "\n\n".join(lines)

        if lines:
            return "\n\n".join(lines)
        return f"No schedule tick traces found{f' for {ticker_symbol}' if ticker_symbol else ''}."

    @classmethod
    def _format_trace_detail(cls, t: ScheduleTickTrace) -> str:
        ts_str = cls._fmt_ts(t.timestamp)
        lines = [
            f"[Tick Trace {t.tick_id}] ({t.ticker_symbol} on {t.exchange} @ {ts_str}, Schedule: {t.schedule})",
            f"  1. Market Data Check: Fresh={t.market_data_fresh} "
            f"(Age: {t.candle_age_seconds:.1f}s, Close: ${t.close_price or 'N/A'})",
        ]
        if t.strategy_evaluations:
            strat_parts = [
                f"{name}={info.get('signal', 'HOLD')} (weight={info.get('weight', 1.0)}, {info.get('latency_ms', 0)}ms)"
                for name, info in sorted(t.strategy_evaluations.items())
            ]
            lines.append(f"  2. Strategy Evaluations: {', '.join(strat_parts)}")
        else:
            lines.append("  2. Strategy Evaluations: None recorded")

        lines.append(
            f"  3. Consensus Evaluation: Quorum={t.consensus_quorum} "
            f"(Vote Ratio: {t.vote_ratio * 100:.1f}% vs Threshold: {t.quorum_threshold * 100:.1f}%, "
            f"Winner: {t.winning_strategy or 'None'})"
        )
        if t.risk_passed is not None:
            guard_str = ", ".join(
                f"{g.get('guard_name')}:{'PASS' if g.get('passed') else 'FAIL'}"
                for g in t.guard_evaluations
            ) or "Standard checks"
            lines.append(f"  4. Risk & Guard Check: Passed={t.risk_passed} ({guard_str})")
        else:
            lines.append("  4. Risk & Guard Check: Not reached")

        if t.order_id:
            lat = f", Latency: {t.execution_latency_ms:.0f}ms" if t.execution_latency_ms is not None else ""
            lines.append(
                f"  5. Order Execution: Order={t.order_id} (Decision={t.decision_id or 'N/A'}, "
                f"Status={t.order_status or 'UNKNOWN'}{lat})"
            )
            lines.append(
                f"  6. Reconciliation: Reconciled={t.reconciled} "
                f"({t.reconciliation_note or 'Verified against exchange state'})"
            )
        else:
            lines.append(
                f"  5. Terminal Outcome: NO_ORDER at stage '{t.terminal_stage}' "
                f"(Reason: {t.no_order_reason or 'Quorum or guard not met'})"
            )
        return "\n".join(lines)

    @staticmethod
    def _fmt_ts(ts: Optional[float]) -> str:
        if ts is None:
            return "Never"
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
