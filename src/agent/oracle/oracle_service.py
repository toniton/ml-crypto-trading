from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

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

        total_cash = Decimal("0")
        total_crypto_val = Decimal("0")
        cash_seen = False

        for symbol in sorted(context.symbols):
            symbol_context = context.symbols[symbol]
            base, quote = symbol.split("_") if "_" in symbol else (symbol, "USD")

            if symbol_context.balance is not None and not cash_seen:
                total_cash = symbol_context.balance
                cash_seen = True

            if symbol_context.position is not None and symbol_context.current_price is not None:
                total_crypto_val += symbol_context.position * symbol_context.current_price

            price_str = f"${symbol_context.current_price:f} {quote}" if symbol_context.current_price is not None else "None"
            pos_str = f"{symbol_context.position:f} {base}" if symbol_context.position is not None else f"0 {base}"
            bal_str = f"${symbol_context.balance:f} {quote}" if symbol_context.balance is not None else "None"
            pnl_str = f"${symbol_context.pnl:f} {quote}" if symbol_context.pnl is not None else f"$0 {quote}"
            dd_str = f"{symbol_context.drawdown:f}%" if symbol_context.drawdown is not None else "0%"

            lines.append(f"- {symbol}:")
            lines.append(f"    price={price_str}")
            lines.append(f"    position={pos_str}")
            lines.append(f"    balance={bal_str}")
            lines.append(f"    pnl={pnl_str}")
            lines.append(f"    drawdown={dd_str}")
            lines.append(f"    recent orders={len(symbol_context.recent_orders)}")
            lines.append(f"    recent executions={len(symbol_context.recent_executions)}")
            for execution in symbol_context.recent_executions[-5:]:
                lines.append(
                    f"      fill: {execution.action} {execution.quantity} @ ${execution.price:f} {quote} "
                    f"(fee={execution.fee})"
                )

        if not context.symbols:
            lines.append("- (no market/trading events observed yet)")
        else:
            quote_currency = next(
                (symbol.split("_")[1] for symbol in sorted(context.symbols) if "_" in symbol),
                "USD"
            )
            total_equity = total_cash + total_crypto_val
            exposure_pct = (total_crypto_val / total_equity * Decimal("100")) if total_equity > Decimal("0") else Decimal("0")
            lines += [
                "",
                "Ground Truth Portfolio State:",
                f"- Cash Balance: ${total_cash:f} {quote_currency}",
                f"- Crypto Holdings Market Value: ${total_crypto_val:f} {quote_currency}",
                f"- Total Account Equity: ${total_equity:f} {quote_currency}",
                f"- Crypto Exposure: {exposure_pct:.2f}% of total equity",
            ]

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
