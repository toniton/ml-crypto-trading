from __future__ import annotations

from decimal import Decimal

from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.events.message_event_bus import MessageEventBus
from src.trading.activity.asset_activity_tracker import AssetActivityTracker
from src.trading.events import (
    MarketDataEvent,
    OrderExecuted,
    OrderSubmitted,
    SignalGeneratedEvent,
    StrategyEvaluatedEvent,
)


def _order(ticker: str, created: float, executed: float | None = None) -> Order:
    return Order(
        uuid="o1",
        provider_name="CRYPTO_DOT_COM",
        ticker_symbol=ticker,
        price=Decimal("100"),
        quantity="0.01",
        trade_action=TradeAction.BUY,
        created_time=created,
        executed_time=executed,
    )


def test_tracks_all_activity_signals():
    bus = MessageEventBus()
    tracker = AssetActivityTracker()
    tracker.subscribe(bus)

    bus.publish(MarketDataEvent(
        ticker_symbol="BTC_USD",
        market_data=MarketData(
            volume=Decimal("1"), high_price=Decimal("2"),
            low_price=Decimal("1"), close_price=Decimal("1.5"),
            timestamp=100.0,
        ),
    ))
    bus.publish(StrategyEvaluatedEvent(symbol="BTC_USD", evaluated_at=200.0))
    bus.publish(SignalGeneratedEvent(symbol="BTC_USD", action="BUY", generated_at=300.0))
    bus.publish(OrderSubmitted(symbol="BTC_USD", order=_order("BTC_USD", 400.0)))
    bus.publish(OrderExecuted(symbol="BTC_USD", order=_order("BTC_USD", 400.0, executed=500.0)))

    state = tracker.state_for("BTC_USD")
    assert state is not None
    assert state.last_market_data_at == 100.0
    assert state.last_evaluation_at == 200.0
    assert state.last_signal_at == 300.0
    assert state.last_order_at == 400.0
    assert state.last_execution_at == 500.0
    assert state.last_activity_at == 500.0


def test_ignores_outdated_updates():
    bus = MessageEventBus()
    tracker = AssetActivityTracker()
    tracker.subscribe(bus)

    bus.publish(StrategyEvaluatedEvent(symbol="BTC_USD", evaluated_at=200.0))
    bus.publish(StrategyEvaluatedEvent(symbol="BTC_USD", evaluated_at=150.0))

    assert tracker.state_for("BTC_USD").last_evaluation_at == 200.0


def test_cold_start_no_activity():
    bus = MessageEventBus()
    tracker = AssetActivityTracker()
    tracker.subscribe(bus)
    assert tracker.state_for("BTC_USD") is None
    assert tracker.started_at > 0


def test_execution_falls_back_to_created_time():
    bus = MessageEventBus()
    tracker = AssetActivityTracker()
    tracker.subscribe(bus)
    bus.publish(OrderExecuted(symbol="BTC_USD", order=_order("BTC_USD", 400.0)))
    assert tracker.state_for("BTC_USD").last_execution_at == 400.0