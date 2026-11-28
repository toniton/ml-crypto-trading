from __future__ import annotations

from typing import Callable
from uuid import uuid4

from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.core.interfaces.event_subscription import EventSubscription


class BacktestCallbackSubscription(EventSubscription):
    def __init__(self, callback: Callable[[Event], None]) -> None:
        self._callback = callback

    def put(self, event: Event) -> None:
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

    def publish(self, event: Event) -> None:
        subscribers = list(self._subscriptions.get(event.type, {}).values())
        for subscription in subscribers:
            subscription.put(event)

    def close(self) -> None:
        self._subscriptions.clear()

    def subscribe_callback(
            self,
            event_class: type[Event],
            callback: Callable[[Event], None],
    ) -> str:
        if not (isinstance(event_class, type) and issubclass(event_class, Event)):
            raise TypeError(
                f"subscribe_callback requires an Event subclass, got {event_class!r}"
            )
        return self.subscribe(event_class.__name__, BacktestCallbackSubscription(callback))


class BacktestDiagnosticEventBus(EventBus):
    """Forwards only allowlisted diagnostic events to a BacktestEventBus."""

    def __init__(
            self,
            delegate: BacktestEventBus,
            allowed_event_types: frozenset[str],
    ) -> None:
        self._delegate = delegate
        self._allowed_event_types = allowed_event_types

    def subscribe(self, event_type: str, subscription: EventSubscription) -> str:
        return self._delegate.subscribe(event_type, subscription)

    def unsubscribe(self, subscription_id: str) -> None:
        self._delegate.unsubscribe(subscription_id)

    def publish(self, event: Event) -> None:
        if event.type in self._allowed_event_types:
            self._delegate.publish(event)

    def close(self) -> None:
        return None
