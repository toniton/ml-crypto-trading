from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.agent.oracle.events import (
    ORACLE_EVENT_TYPES,
    OracleSummaryEvent,
)
from src.agent.oracle.oracle_adapter import OracleEventAdapter
from src.agent.oracle.oracle_context import OracleContext, SymbolContext
from src.agent.oracle.oracle_summary import OracleSummary
from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.core.interfaces.llm_adapter import LlmAdapter
from src.events.message_event_bus import CallbackSubscription
from src.logging.agent_logging_mixin import AgentLoggingMixin

DEFAULT_FAILURE_COOLDOWN = timedelta(seconds=60)
ORACLE_SYSTEM_PROMPT = (
    "You are an AI quantitative trading oracle. Analyze and summarize the provided "
    "accumulated market and trading state for the trading agent based solely on the provided context."
)


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
            failure_cooldown: timedelta | None = None,
    ):
        self._llm = llm
        self._context = context or OracleContext()
        self._adapter = OracleEventAdapter()
        self._publish_bus = publish_bus
        self._model = model
        self._model_version = model_version
        self._failure_cooldown = failure_cooldown or DEFAULT_FAILURE_COOLDOWN
        self._latest_summary: OracleSummary | None = None
        self._subscription_ids: list[str] = []
        self._lock = threading.RLock()
        self._is_generating = False

    @property
    def context(self) -> OracleContext:
        return self._context

    def observe(self, event: Event) -> None:
        """Consume a single domain event, then summarize if the interval is due."""
        with self._lock:
            self._adapter.apply(event, self._context)
        try:
            summary = self.summarize_if_due()
            if summary is not None:
                self._publish(summary)
        except Exception as exc:
            self.agent_logger.warning("Failed to generate Oracle summary on event %s: %s", type(event).__name__, exc)

    def summarize(self, now: datetime | None = None) -> OracleSummary | None:
        now = now or datetime.now(timezone.utc)
        with self._lock:
            if self._is_generating:
                return self._latest_summary
            self._is_generating = True
            self._context.mark_summarized(now)
        try:
            summary = self._analyze(now)
            with self._lock:
                self._latest_summary = summary
            return summary
        except Exception:
            cooldown = min(self._failure_cooldown, self._context.summary_interval)
            cooldown_at = now - self._context.summary_interval + cooldown
            with self._lock:
                self._context.mark_summarized(cooldown_at)
            raise
        finally:
            with self._lock:
                self._is_generating = False

    def summarize_if_due(self, now: datetime | None = None) -> OracleSummary | None:
        now = now or datetime.now(timezone.utc)
        with self._lock:
            if self._is_generating or not self._context.is_due(now):
                return None
        return self.summarize(now)

    def get_latest_summary(self) -> OracleSummary | None:
        with self._lock:
            return self._latest_summary

    def subscribe(self, event_bus: EventBus) -> list[str]:
        """Register this service as a handler for Oracle-relevant event types."""
        with self._lock:
            for event_type in ORACLE_EVENT_TYPES:
                subscription_id = event_bus.subscribe(event_type, CallbackSubscription(self.observe))
                self._subscription_ids.append(subscription_id)
            return list(self._subscription_ids)

    def _analyze(self, generated_at: datetime) -> OracleSummary:
        with self._lock:
            prompt = self._build_prompt(self._context)
            market_state, trading_state, risk_state = self._derive_states(self._context)
            session_id = self._context.session_id
            primary_symbol = self._primary_symbol(self._context)
        self.agent_logger.info("Generating Oracle summary from accumulated context...")
        summary_text = self._llm.generate(prompt, system_prompt=ORACLE_SYSTEM_PROMPT)
        return OracleSummary(
            summary=summary_text,
            market_state=market_state,
            trading_state=trading_state,
            risk_state=risk_state,
            generated_at=generated_at,
            session_id=session_id,
            symbol=primary_symbol,
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

    @classmethod
    def _build_prompt(cls, context: OracleContext) -> str:
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
            sym_ctx = context.symbols[symbol]
            if sym_ctx.balance is not None and not cash_seen:
                total_cash = sym_ctx.balance
                cash_seen = True

            if sym_ctx.position is not None and sym_ctx.current_price is not None:
                total_crypto_val += sym_ctx.position * sym_ctx.current_price

            lines.extend(cls._format_symbol_context(symbol, sym_ctx))

        if not context.symbols:
            lines.append("- (no market/trading events observed yet)")
        else:
            quote_currency = next(
                (symbol.split("_")[1] for symbol in sorted(context.symbols) if "_" in symbol),
                "USD",
            )
            total_equity = total_cash + total_crypto_val
            exposure_pct = (
                (total_crypto_val / total_equity * Decimal("100"))
                if total_equity > Decimal("0")
                else Decimal("0")
            )
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
    def _format_symbol_context(symbol: str, ctx: SymbolContext) -> list[str]:
        base, quote = symbol.split("_") if "_" in symbol else (symbol, "USD")
        price_str = f"${ctx.current_price:f} {quote}" if ctx.current_price is not None else "None"
        pos_str = f"{ctx.position:f} {base}" if ctx.position is not None else f"0 {base}"
        bal_str = f"${ctx.balance:f} {quote}" if ctx.balance is not None else "None"
        pnl_str = f"${ctx.pnl:f} {quote}" if ctx.pnl is not None else f"$0 {quote}"
        dd_str = f"{ctx.drawdown:f}%" if ctx.drawdown is not None else "0%"

        lines = [
            f"- {symbol}:",
            f"    price={price_str}",
            f"    position={pos_str}",
            f"    balance={bal_str}",
            f"    pnl={pnl_str}",
            f"    drawdown={dd_str}",
            f"    recent orders={len(ctx.recent_orders)}",
            f"    recent executions={len(ctx.recent_executions)}",
        ]
        for execution in ctx.recent_executions[-5:]:
            lines.append(
                f"      fill: {execution.action} {execution.quantity} @ ${execution.price:f} {quote} "
                f"(fee={execution.fee})"
            )
        return lines

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
