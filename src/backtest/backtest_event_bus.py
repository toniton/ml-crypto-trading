from __future__ import annotations

from typing import Callable
from uuid import uuid4

from src.backtest.events import BacktestEvent
from src.core.interfaces.event_bus import EventBus
from src.core.interfaces.event_subscription import EventSubscription


class BacktestCallbackSubscription(EventSubscription):
    def __init__(self, callback: Callable[[BacktestEvent], None]) -> None:
        self._callback = callback

    def put(self, event: BacktestEvent) -> None:
        if not isinstance(event, BacktestEvent):
            raise TypeError(
                f"Expected a BacktestEvent, got {type(event).__name__}"
            )
        self._callback(event)

    def close(self) -> None:
        self._callback = lambda _event: None


class BacktestEventBus(EventBus):
    def __init__(self):
        self._subscriptions: dict[str, dict[str, EventSubscription]] = {}

    def subscribe(self, event_type: str, subscription: EventSubscription) -> str:
        subscription_id = uuid4().hex
        self._subscriptions.setdefault(event_type, {})[subscription_id] = subscription
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        for subscribers in self._subscriptions.values():
            if subscription_id in subscribers:
                del subscribers[subscription_id]
                return

    def publish(self, event: BacktestEvent) -> None:
        if not isinstance(event, BacktestEvent):
            raise TypeError(
                f"BacktestEventBus only publishes BacktestEvent instances, "
                f"got {type(event).__name__}"
            )
        subscribers = list(self._subscriptions.get(event.type, {}).values())
        for subscription in subscribers:
            subscription.put(event)

    def close(self) -> None:
        self._subscriptions.clear()

    def subscribe_callback(
            self,
            event_class: type[BacktestEvent],
            callback: Callable[[BacktestEvent], None],
    ) -> str:
        if not (isinstance(event_class, type) and issubclass(event_class, BacktestEvent)):
            raise TypeError(
                f"subscribe_callback requires a BacktestEvent subclass, got {event_class!r}"
            )
        return self.subscribe(event_class.__name__, BacktestCallbackSubscription(callback))
