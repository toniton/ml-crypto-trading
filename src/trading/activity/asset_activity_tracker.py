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

    def _touch(
            self,
            ticker_symbol: str,
            last_market_data_at: Optional[float] = None,
            last_evaluation_at: Optional[float] = None,
            last_signal_at: Optional[float] = None,
            last_order_at: Optional[float] = None,
            last_execution_at: Optional[float] = None,
    ) -> None:
        with self._lock:
            state = self._states.setdefault(ticker_symbol, AssetActivityState(ticker_symbol=ticker_symbol))
            if last_market_data_at is not None:
                state.last_market_data_at = self._max_timestamp(state.last_market_data_at, last_market_data_at)
            if last_evaluation_at is not None:
                state.last_evaluation_at = self._max_timestamp(state.last_evaluation_at, last_evaluation_at)
            if last_signal_at is not None:
                state.last_signal_at = self._max_timestamp(state.last_signal_at, last_signal_at)
            if last_order_at is not None:
                state.last_order_at = self._max_timestamp(state.last_order_at, last_order_at)
            if last_execution_at is not None:
                state.last_execution_at = self._max_timestamp(state.last_execution_at, last_execution_at)

    @staticmethod
    def _max_timestamp(current: Optional[float], candidate: float) -> float:
        return candidate if current is None or candidate > current else current

    def state_for(self, ticker_symbol: str) -> Optional[AssetActivityState]:
        with self._lock:
            state = self._states.get(ticker_symbol)
            return dataclasses.replace(state) if state is not None else None

    def states(self) -> list[AssetActivityState]:
        with self._lock:
            return [dataclasses.replace(s) for s in self._states.values()]
