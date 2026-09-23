import dataclasses
import threading
import time
from typing import Callable, Optional

from src.agent.monitoring.activity_state import ActivityStateProvider, AssetActivityState
from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.events.message_event_bus import CallbackSubscription
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.events import (
    MarketDataEvent,
    MarketStateChanged,
    OrderExecuted,
    OrderSubmitted,
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
        for event_type in (
                "MarketDataEvent",
                "MarketStateChanged",
                "StrategyEvaluatedEvent",
                "SignalGeneratedEvent",
                "OrderSubmitted",
                "OrderExecuted",
        ):
            self._subscriptions.append(
                event_bus.subscribe(event_type, CallbackSubscription(self._on_event))
            )

    def _on_event(self, event: Event) -> None:
        handler: Optional[Callable[[Event], None]] = getattr(
            self, f"_on_{type(event).__name__}", None
        )
        if handler is not None:
            handler(event)

    def _on_MarketDataEvent(self, event: MarketDataEvent) -> None:
        self._touch(event.ticker_symbol, last_market_data_at=event.market_data.timestamp)

    def _on_MarketStateChanged(self, event: MarketStateChanged) -> None:
        self._touch(event.symbol, last_market_data_at=event.market_timestamp)

    def _on_StrategyEvaluatedEvent(self, event: StrategyEvaluatedEvent) -> None:
        self._touch(event.symbol, last_evaluation_at=event.evaluated_at)

    def _on_SignalGeneratedEvent(self, event: SignalGeneratedEvent) -> None:
        self._touch(event.symbol, last_signal_at=event.generated_at)

    def _on_OrderSubmitted(self, event: OrderSubmitted) -> None:
        self._touch(event.symbol, last_order_at=event.order.created_time)

    def _on_OrderExecuted(self, event: OrderExecuted) -> None:
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
