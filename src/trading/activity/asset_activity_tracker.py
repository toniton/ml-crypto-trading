import dataclasses
import threading
import time
from typing import Optional

from src.agent.monitoring.activity_state import ActivityStateProvider, AssetActivityState
from src.core.interfaces.event_bus import EventBus
from src.events.message_event_bus import CallbackSubscription
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.events import (
    MarketDataEvent,
    MarketStateChangedEvent,
    OrderFilledEvent,
    OrderSubmittedEvent,
    SignalGeneratedEvent,
    StrategyEvaluatedEvent,
)


class AssetActivityTracker(ActivityStateProvider, ApplicationLoggingMixin):
    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._started_at = time.time()
        self._lock = threading.Lock()
        self._states: dict[str, AssetActivityState] = {}
        self._subscriptions: list[str] = []

    @property
    def started_at(self) -> float:
        return self._started_at

    def subscribe(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._subscriptions.extend([
            event_bus.subscribe(MarketDataEvent.__name__, CallbackSubscription(self._on_market_data)),
            event_bus.subscribe(MarketStateChangedEvent.__name__, CallbackSubscription(self._on_market_state_changed)),
            event_bus.subscribe(StrategyEvaluatedEvent.__name__, CallbackSubscription(self._on_strategy_evaluated)),
            event_bus.subscribe(SignalGeneratedEvent.__name__, CallbackSubscription(self._on_signal_generated)),
            event_bus.subscribe(OrderSubmittedEvent.__name__, CallbackSubscription(self._on_order_submitted)),
            event_bus.subscribe(OrderFilledEvent.__name__, CallbackSubscription(self._on_order_filled)),
        ])

    def _on_market_data(self, event: MarketDataEvent) -> None:
        self._touch(event.ticker_symbol, last_market_data_at=event.market_data.timestamp)

    def _on_market_state_changed(self, event: MarketStateChangedEvent) -> None:
        self._touch(event.symbol, last_market_data_at=event.market_timestamp)

    def _on_strategy_evaluated(self, event: StrategyEvaluatedEvent) -> None:
        self._touch(event.symbol, last_evaluation_at=event.evaluated_at)

    def _on_signal_generated(self, event: SignalGeneratedEvent) -> None:
        self._touch(event.symbol, last_signal_at=event.generated_at)

    def _on_order_submitted(self, event: OrderSubmittedEvent) -> None:
        self._touch(event.symbol, last_order_at=event.order.created_time)

    def _on_order_filled(self, event: OrderFilledEvent) -> None:
        executed_at = event.order.executed_time or event.order.created_time
        self._touch(event.symbol, last_execution_at=executed_at)

    def _touch(self, ticker_symbol: str, **values: float) -> None:
        with self._lock:
            state = self._states.setdefault(ticker_symbol, AssetActivityState(ticker_symbol=ticker_symbol))
            for field, value in values.items():
                if value is None:
                    continue
                current = getattr(state, field)
                if current is None or value > current:
                    setattr(state, field, value)

    def state_for(self, ticker_symbol: str) -> Optional[AssetActivityState]:
        with self._lock:
            state = self._states.get(ticker_symbol)
            return dataclasses.replace(state) if state is not None else None

    def states(self) -> list[AssetActivityState]:
        with self._lock:
            return [dataclasses.replace(s) for s in self._states.values()]
