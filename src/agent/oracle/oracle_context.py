from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from api.interfaces.asset_schedule import AssetSchedule
from src.trading.scheduling.asset_schedule_registry import AssetScheduleRegistry

MAX_OBSERVATIONS = 50


def summary_interval_for(schedule: AssetSchedule) -> timedelta:
    """Translate an :class:`AssetSchedule` into a summary interval duration."""
    return timedelta(seconds=AssetScheduleRegistry.UNIT_SECONDS[schedule])


@dataclass
class OrderObservation:
    order_id: str
    symbol: str | None
    action: str | None
    quantity: Decimal
    price: Decimal | None
    status: str | None
    timestamp: datetime | None


@dataclass
class ExecutionObservation:
    order_id: str
    symbol: str | None
    action: str | None
    quantity: Decimal
    price: Decimal | None
    fee: Decimal | None
    timestamp: datetime | None


@dataclass
class SymbolContext:
    """Bounded, per-symbol state accumulated from trading and market events."""

    symbol: str
    current_price: Decimal | None = None
    balance: Decimal | None = None
    position: Decimal | None = None
    pnl: Decimal | None = None
    drawdown: Decimal | None = None
    recent_orders: list[OrderObservation] = field(default_factory=list)
    recent_executions: list[ExecutionObservation] = field(default_factory=list)

    def add_order(self, observation: OrderObservation) -> None:
        self.recent_orders.append(observation)
        if len(self.recent_orders) > MAX_OBSERVATIONS:
            self.recent_orders = self.recent_orders[-MAX_OBSERVATIONS:]

    def add_execution(self, observation: ExecutionObservation) -> None:
        self.recent_executions.append(observation)
        if len(self.recent_executions) > MAX_OBSERVATIONS:
            self.recent_executions = self.recent_executions[-MAX_OBSERVATIONS:]


@dataclass
class OracleContext:
    """Accumulated trading state with interval tracking for summary gating."""

    session_id: str | None = None
    summary_interval: timedelta = field(default_factory=lambda: timedelta(hours=1))
    last_summary_at: datetime | None = None
    symbols: dict[str, SymbolContext] = field(default_factory=dict)

    def symbol(self, key: str) -> SymbolContext:
        if key is None:
            raise ValueError("Cannot resolve a SymbolContext for a missing symbol.")
        context = self.symbols.get(key)
        if context is None:
            context = SymbolContext(symbol=key)
            self.symbols[key] = context
        return context

    def is_due(self, now: datetime) -> bool:
        if self.last_summary_at is None:
            return True
        return (now - self.last_summary_at) >= self.summary_interval

    def mark_summarized(self, generated_at: datetime) -> None:
        self.last_summary_at = generated_at
