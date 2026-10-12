from __future__ import annotations

from decimal import Decimal

from api.interfaces.trade_action import OrderStatus
from src.events.message_event_bus import CallbackSubscription


def _capture(stack, event_type: str) -> list:
    captured = []

    def handler(event):
        captured.append(event)

    stack.trading_bus.subscribe(event_type, CallbackSubscription(handler))
    return captured


def test_simulated_trading_executes_order_end_to_end(e2e_stack):
    stack = e2e_stack
    submitted = _capture(stack, "OrderSubmittedEvent")
    filled = _capture(stack, "OrderFilledEvent")
    evaluated = _capture(stack, "StrategyEvaluatedEvent")
    signals = _capture(stack, "SignalGeneratedEvent")
    market = _capture(stack, "MarketDataEvent")

    # 1. Seed a market price that triggers the "close > 100" buy strategy.
    stack.seed_market_data(close=Decimal("150"))
    assert len(market) == 1
    assert stack.tracker.state_for("BTC_USD").last_market_data_at is not None

    # 2. Drive a strategy evaluation cycle.
    stack.trading_executor.create_buy_order(stack.assets)

    assert len(evaluated) == 1, "strategy evaluation must be emitted"
    assert len(signals) >= 1, "a consensus signal must be generated"
    assert len(submitted) == 1, "an order must be submitted"
    order = submitted[0].order

    # 3. Simulate the exchange fill callback.
    stack.complete_fill(order)
    assert len(filled) == 1, "an order-filled event must be published"

    # 4. Journal reflects the live fill.
    entries = stack.journal.entries("BTC_USD")
    assert len(entries) == 1
    assert entries[0].status == OrderStatus.COMPLETED

    # 5. Activity tracker saw the full pipeline.
    state = stack.tracker.state_for("BTC_USD")
    assert state.last_evaluation_at is not None
    assert state.last_signal_at is not None
    assert state.last_order_at is not None
    assert state.last_execution_at is not None
    assert state.last_activity_at == state.last_execution_at


def test_simulated_no_signal_when_conditions_not_met(e2e_stack):
    stack = e2e_stack
    submitted = _capture(stack, "OrderSubmittedEvent")
    signals = _capture(stack, "SignalGeneratedEvent")

    # Price below the "close > 100" threshold -> no signal, no order.
    stack.seed_market_data(close=Decimal("50"))
    stack.trading_executor.create_buy_order(stack.assets)

    assert not signals, "no consensus signal expected below threshold"
    assert not submitted, "no order expected without a signal"

    tracker_state = stack.tracker.state_for("BTC_USD")
    assert tracker_state.last_market_data_at is not None
    assert tracker_state.last_signal_at is None
