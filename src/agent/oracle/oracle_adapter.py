from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from api.interfaces.trade_action import TradeAction
from src.agent.oracle.oracle_context import (
    ExecutionObservation,
    OracleContext,
    OrderObservation,
)
from src.backtest.events import (
    BalanceUpdateEvent,
    OrderCancelledEvent as BacktestOrderCancelledEvent,
    OrderFilledEvent as BacktestOrderFilledEvent,
    OrderSubmittedEvent as BacktestOrderSubmittedEvent,
    PortfolioSnapshotEvent,
)
from src.core.interfaces.event import Event
from src.trading.events import (
    BalanceChangedEvent,
    MarketDataEvent,
    MarketStateChangedEvent,
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderSubmittedEvent,
    PositionChangedEvent,
)


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return None


def _action_of(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, TradeAction):
        return value.value
    return str(value)


def _to_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


class OracleEventAdapter:
    """Adapts domain events into bounded :class:`OracleContext` updates.

    This is the single place that knows how trading/market events map onto the
    Oracle's state, keeping :class:`OracleService` decoupled from every domain
    event emitted by the trading or backtest subsystems.
    """

    def apply(self, event: Event, context: OracleContext) -> None:
        if isinstance(event, (MarketDataEvent, MarketStateChangedEvent)):
            self._apply_market_event(event, context)
        elif isinstance(event, (
                OrderSubmittedEvent, BacktestOrderSubmittedEvent,
                OrderFilledEvent, BacktestOrderFilledEvent,
                OrderCancelledEvent, BacktestOrderCancelledEvent,
        )):
            self._apply_order_event(event, context)
        elif isinstance(event, (
                PositionChangedEvent, PortfolioSnapshotEvent,
                BalanceChangedEvent, BalanceUpdateEvent,
        )):
            self._apply_account_event(event, context)

    @staticmethod
    def _apply_market_event(
            event: MarketDataEvent | MarketStateChangedEvent,
            context: OracleContext,
    ) -> None:
        if isinstance(event, MarketDataEvent):
            price = _to_decimal(event.market_data.close_price)
            if price is not None:
                context.symbol(event.ticker_symbol).current_price = price
        elif isinstance(event, MarketStateChangedEvent):
            price = _to_decimal(event.price)
            if price is not None:
                context.symbol(event.symbol).current_price = price

    def _apply_order_event(self, event: Event, context: OracleContext) -> None:
        if isinstance(event, (OrderSubmittedEvent, BacktestOrderSubmittedEvent)):
            context.symbol(event.order.ticker_symbol).add_order(self._order_observation(event.order))
        elif isinstance(event, (OrderFilledEvent, BacktestOrderFilledEvent)):
            symbol_context = context.symbol(event.order.ticker_symbol)
            symbol_context.add_order(self._order_observation(event.order, status="COMPLETED"))
            execution = self._execution_observation(event)
            if execution is not None:
                symbol_context.add_execution(execution)
        elif isinstance(event, (OrderCancelledEvent, BacktestOrderCancelledEvent)):
            context.symbol(event.order.ticker_symbol).add_order(
                self._order_observation(event.order, status="CANCELLED")
            )

    @staticmethod
    def _apply_account_event(event: Event, context: OracleContext) -> None:
        if isinstance(event, PositionChangedEvent):
            symbol_context = context.symbol(event.symbol)
            symbol_context.position = _to_decimal(event.position_qty)
            symbol_context.pnl = _to_decimal(event.realized_pnl)
        elif isinstance(event, PortfolioSnapshotEvent):
            symbol_context = context.symbol(event.ticker_symbol)
            positions = event.snapshot.positions or {}
            if isinstance(positions, dict):
                pos = positions.get(event.ticker_symbol)
                if pos is not None:
                    symbol_context.position = _to_decimal(pos)
        elif isinstance(event, BalanceChangedEvent):
            balance = _to_decimal(event.balance)
            if balance is not None:
                context.symbol(event.symbol).balance = balance
        elif isinstance(event, BalanceUpdateEvent):
            for balance in event.balances:
                amount = _to_decimal(balance.available_balance)
                if balance.currency is None or amount is None:
                    continue
                for symbol_key, symbol_context in context.symbols.items():
                    base = symbol_key.split("_")[0] if "_" in symbol_key else symbol_key
                    if base == balance.currency:
                        symbol_context.balance = amount

    @staticmethod
    def _order_observation(order, status: str | None = None) -> OrderObservation:
        order_status = status or (order.status.value if order.status is not None else "")
        return OrderObservation(
            order_id=order.uuid,
            symbol=order.ticker_symbol,
            action=_action_of(order.trade_action),
            quantity=_to_decimal(order.quantity) or Decimal(0),
            price=_to_decimal(order.price),
            status=order_status,
            timestamp=_to_datetime(order.created_time),
        )

    @staticmethod
    def _execution_observation(event: Event) -> ExecutionObservation | None:
        if not isinstance(event, (OrderFilledEvent, BacktestOrderFilledEvent)) or event.order is None:
            return None
        order = event.order
        if isinstance(event, BacktestOrderFilledEvent) and event.execution is not None:
            price = _to_decimal(event.execution.execution_price)
            quantity = _to_decimal(event.execution.executed_quantity) or Decimal(0)
            fee = _to_decimal(event.execution.fee)
            timestamp = _to_datetime(event.execution.executed_at)
        else:
            price = _to_decimal(order.fill_price or order.price)
            quantity = _to_decimal(order.quantity) or Decimal(0)
            fee = _to_decimal(order.fees)
            timestamp = _to_datetime(order.executed_time or order.created_time)

        return ExecutionObservation(
            order_id=order.uuid,
            symbol=order.ticker_symbol,
            action=_action_of(order.trade_action),
            quantity=quantity,
            price=price,
            fee=fee,
            timestamp=timestamp,
        )
