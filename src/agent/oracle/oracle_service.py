from __future__ import annotations

from datetime import datetime, timezone

from src.agent.oracle.events import (
    ORACLE_EVENT_TYPES,
    OracleSummaryEvent,
)
from src.agent.oracle.oracle_adapter import OracleEventAdapter
from src.agent.oracle.oracle_context import OracleContext
from src.agent.oracle.oracle_summary import OracleSummary
from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.core.interfaces.llm_adapter import LlmAdapter
from src.events.message_event_bus import CallbackSubscription
from src.logging.agent_logging_mixin import AgentLoggingMixin


class OracleService(AgentLoggingMixin):
    """Event-driven orchestration layer around the Oracle.

    Responsibilities: event accumulation, interval gating, LLM analysis, summary
    creation and publication. It does not own scheduling threads.
    """

    def __init__(
            self,
            llm: LlmAdapter,
            context: OracleContext | None = None,
            *,
            publish_bus: EventBus | None = None,
            model: str | None = None,
            model_version: str | None = None,
    ):
        self._llm = llm
        self._context = context or OracleContext()
        self._adapter = OracleEventAdapter()
        self._publish_bus = publish_bus
        self._model = model
        self._model_version = model_version
        self._latest_summary: OracleSummary | None = None
        self._subscription_ids: list[str] = []

    @property
    def context(self) -> OracleContext:
        return self._context

    def observe(self, event: Event) -> None:
        """Consume a single domain event, then summarize if the interval is due."""
        self._adapter.apply(event, self._context)
        summary = self.summarize_if_due()
        if summary is not None:
            self._publish(summary)

    def summarize(self, now: datetime | None = None) -> OracleSummary:
        now = now or datetime.now(timezone.utc)
        summary = self._analyze(now)
        self._context.mark_summarized(summary.generated_at)
        self._latest_summary = summary
        return summary

    def summarize_if_due(self, now: datetime | None = None) -> OracleSummary | None:
        now = now or datetime.now(timezone.utc)
        if not self._context.is_due(now):
            return None
        return self.summarize(now)

    def get_latest_summary(self) -> OracleSummary | None:
        return self._latest_summary

    def subscribe(self, event_bus: EventBus) -> list[str]:
        """Register this service as a handler for Oracle-relevant event types."""
        for event_type in ORACLE_EVENT_TYPES:
            subscription_id = event_bus.subscribe(event_type, CallbackSubscription(self.observe))
            self._subscription_ids.append(subscription_id)
        return self._subscription_ids

    def _analyze(self, generated_at: datetime) -> OracleSummary:
        prompt = self._build_prompt(self._context)
        self.agent_logger.info("Generating Oracle summary from accumulated context...")
        summary_text = self._llm.generate(prompt)
        market_state, trading_state, risk_state = self._derive_states(self._context)
        return OracleSummary(
            summary=summary_text,
            market_state=market_state,
            trading_state=trading_state,
            risk_state=risk_state,
            generated_at=generated_at,
            session_id=self._context.session_id,
            symbol=self._primary_symbol(self._context),
            model=self._model,
            model_version=self._model_version,
        )

    def _publish(self, summary: OracleSummary) -> None:
        if self._publish_bus is None:
            return
        self._publish_bus.publish(OracleSummaryEvent(summary))
        self.agent_logger.info(
            f"Published Oracle summary (correlation={summary.correlation_id})"
        )

    @staticmethod
    def _build_prompt(context: OracleContext) -> str:
        lines = [
            "You are a trading oracle. Summarize the accumulated market and trading "
            "state below for the trading agent.",
            f"Session: {context.session_id or 'unknown'}",
            "",
            "Per-asset context:",
        ]
        for symbol in sorted(context.symbols):
            symbol_context = context.symbols[symbol]
            lines.append(f"- {symbol}:")
            lines.append(f"    price={symbol_context.current_price}")
            lines.append(f"    position={symbol_context.position}")
            lines.append(f"    balance={symbol_context.balance}")
            lines.append(f"    pnl={symbol_context.pnl}")
            lines.append(f"    drawdown={symbol_context.drawdown}")
            lines.append(f"    recent orders={len(symbol_context.recent_orders)}")
            lines.append(f"    recent executions={len(symbol_context.recent_executions)}")
            for execution in symbol_context.recent_executions[-5:]:
                lines.append(
                    f"      fill: {execution.action} {execution.quantity} @ {execution.price} "
                    f"(fee={execution.fee})"
                )

        if not context.symbols:
            lines.append("- (no market/trading events observed yet)")

        lines += [
            "",
            "Produce a concise trading summary covering:",
            "- overall market state",
            "- trading state (positions, recent activity)",
            "- risk state (drawdowns, exposure)",
            "- key observations",
            "- recommended actions (if any)",
        ]
        return "\n".join(lines)

    @staticmethod
    def _derive_states(context: OracleContext) -> tuple[str, str, str]:
        symbols = list(context.symbols.values())
        has_price = any(s.current_price is not None for s in symbols)
        has_position = any((s.position or 0) > 0 for s in symbols)
        has_drawdown = any((s.drawdown or 0) < 0 for s in symbols)
        return (
            "active" if has_price else "unavailable",
            "position_open" if has_position else "flat",
            "drawdown" if has_drawdown else "normal",
        )

    @staticmethod
    def _primary_symbol(context: OracleContext) -> str | None:
        return next(iter(sorted(context.symbols)), None)
