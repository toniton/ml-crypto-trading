from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from src.agent.oracle.oracle_context import (
    ExecutionObservation,
    OracleContext,
    OrderObservation,
)
from src.core.interfaces.event import Event

_MARKET_TYPES = {"MarketStateChanged", "MarketDataEvent", "MarketDataPointEvent"}
_ORDER_SUBMITTED_TYPES = {"OrderSubmitted", "OrderSubmittedEvent"}
_ORDER_FILLED_TYPES = {"OrderExecuted", "OrderFilledEvent"}
_ORDER_CANCELLED_TYPES = {"OrderCancelled", "OrderCancelledEvent"}
_POSITION_TYPES = {"PositionChanged", "PortfolioSnapshotEvent"}
_BALANCE_TYPES = {"BalanceChanged", "BalanceUpdateEvent"}


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
    if hasattr(value, "value"):
        return str(value.value)
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
        event_type = event.type

        if event_type in _MARKET_TYPES:
            self._apply_market_price(event, context)
        elif event_type in _ORDER_SUBMITTED_TYPES:
            self._apply_order(event, context)
        elif event_type in _ORDER_FILLED_TYPES:
            self._apply_order_filled(event, context)
        elif event_type in _ORDER_CANCELLED_TYPES:
            self._apply_order(event, context, status="CANCELLED")
        elif event_type in _POSITION_TYPES:
            self._apply_position(event, context)
        elif event_type in _BALANCE_TYPES:
            self._apply_balance(event, context)

    def _apply_market_price(self, event: Event, context: OracleContext) -> None:
        symbol = getattr(event, "symbol", None) or getattr(event, "ticker_symbol", None)
        price = getattr(event, "price", None)

        market_data = getattr(event, "market_data", None)
        if price is None and market_data is not None:
            price = getattr(market_data, "close_price", None)

        point = getattr(event, "point", None)
        if price is None and point is not None:
            price = getattr(point, "close", None)

        price = _to_decimal(price)
        if symbol and price is not None:
            context.symbol(symbol).current_price = price

    def _apply_order(self, event: Event, context: OracleContext, status: str | None = None) -> None:
        order = getattr(event, "order", None)
        if order is None:
            return
        symbol = getattr(order, "ticker_symbol", None) or getattr(event, "symbol", None)
        if symbol:
            context.symbol(symbol).add_order(self._order_observation(order, status))

    def _apply_order_filled(self, event: Event, context: OracleContext) -> None:
        order = getattr(event, "order", None)
        if order is None:
            return
        symbol = getattr(order, "ticker_symbol", None) or getattr(event, "symbol", None)
        if not symbol:
            return
        symbol_context = context.symbol(symbol)
        symbol_context.add_order(self._order_observation(order, status="COMPLETED"))
        execution = self._execution_observation(event)
        if execution is not None:
            symbol_context.add_execution(execution)

    def _apply_position(self, event: Event, context: OracleContext) -> None:
        symbol = getattr(event, "symbol", None) or getattr(event, "ticker_symbol", None)
        if not symbol:
            return

        symbol_context = context.symbol(symbol)

        position = _to_decimal(getattr(event, "position_qty", None))
        if position is None:
            snapshot = getattr(event, "snapshot", None)
            if snapshot is not None:
                positions = getattr(snapshot, "positions", None) or {}
                if isinstance(positions, dict):
                    position = _to_decimal(positions.get(symbol))

        pnl = _to_decimal(getattr(event, "realized_pnl", None)) or _to_decimal(getattr(event, "pnl", None))
        drawdown = _to_decimal(getattr(event, "drawdown", None))

        if position is not None:
            symbol_context.position = position
        if pnl is not None:
            symbol_context.pnl = pnl
        if drawdown is not None:
            symbol_context.drawdown = drawdown

    def _apply_balance(self, event: Event, context: OracleContext) -> None:
        symbol = getattr(event, "symbol", None)
        if symbol:
            balance = _to_decimal(
                getattr(event, "balance", None) or getattr(event, "available_balance", None)
            )
            if balance is not None:
                context.symbol(symbol).balance = balance
            return

        balances = getattr(event, "balances", None) or []
        if not isinstance(balances, list):
            return
        for balance in balances:
            currency = getattr(balance, "currency", None)
            amount = _to_decimal(getattr(balance, "available_balance", None))
            if currency is None or amount is None:
                continue
            for symbol_key, symbol_context in context.symbols.items():
                base = symbol_key.split("_")[0] if "_" in symbol_key else symbol_key
                if base == currency:
                    symbol_context.balance = amount

    @staticmethod
    def _order_observation(order, status: str | None = None) -> OrderObservation:
        return OrderObservation(
            order_id=str(getattr(order, "uuid", "") or ""),
            symbol=getattr(order, "ticker_symbol", None),
            action=_action_of(getattr(order, "trade_action", None)),
            quantity=_to_decimal(getattr(order, "quantity", None)) or Decimal(0),
            price=_to_decimal(getattr(order, "price", None)),
            status=status or str(getattr(order, "status", None) or ""),
            timestamp=_to_datetime(getattr(order, "created_time", None)),
        )

    @staticmethod
    def _execution_observation(event: Event) -> ExecutionObservation | None:
        order = getattr(event, "order", None)
        if order is None:
            return None

        execution = getattr(event, "execution", None)
        if execution is not None:
            price = _to_decimal(
                getattr(execution, "execution_price", None) or getattr(execution, "price", None)
            )
            quantity = _to_decimal(
                getattr(execution, "executed_quantity", None) or getattr(execution, "quantity", None)
            )
            fee = _to_decimal(getattr(execution, "fee", None))
            timestamp = _to_datetime(
                getattr(execution, "executed_at", None) or getattr(execution, "timestamp", None)
            )
        else:
            price = _to_decimal(getattr(order, "fill_price", None)) or _to_decimal(
                getattr(order, "price", None)
            )
            quantity = _to_decimal(getattr(order, "quantity", None))
            fee = _to_decimal(getattr(order, "fees", None))
            timestamp = _to_datetime(getattr(order, "executed_time", None))

        return ExecutionObservation(
            order_id=str(getattr(order, "uuid", "") or ""),
            symbol=getattr(order, "ticker_symbol", None),
            action=_action_of(getattr(order, "trade_action", None)),
            quantity=quantity or Decimal(0),
            price=price,
            fee=fee,
            timestamp=timestamp,
        )
