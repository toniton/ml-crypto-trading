from __future__ import annotations

import threading
import uuid
from typing import Callable, Optional

from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.core.interfaces.event_subscription import EventSubscription


class CallbackSubscription(EventSubscription):
    def __init__(self, callback: Callable[[Event], None]) -> None:
        self._callback = callback

    def put(self, event: Event) -> None:
        self._callback(event)

    def close(self) -> None:
        self._callback = lambda _event: None


class MessageEventBus(EventBus):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscriptions: dict[str, dict[str, EventSubscription]] = {}

    def subscribe(self, event_type: str, subscription: EventSubscription) -> str:
        subscription_id = uuid.uuid4().hex
        with self._lock:
            self._subscriptions.setdefault(event_type, {})[subscription_id] = subscription
        return subscription_id

    def handler(self, event_type: str):
        def decorator(func: Callable[[Event], None]) -> Callable[[Event], None]:
            self.subscribe(event_type, CallbackSubscription(func))
            return func

        return decorator

    def unsubscribe(self, subscription_id: str) -> None:
        with self._lock:
            for subscribers in self._subscriptions.values():
                if subscription_id in subscribers:
                    del subscribers[subscription_id]
                    return

    def publish(self, event: Event) -> None:
        with self._lock:
            subscribers = list(self._subscriptions.get(event.type, {}).values())
        for subscription in subscribers:
            try:
                subscription.put(event)
            except Exception:  # pylint: disable=broad-except
                continue

    def subscriber_count(self, event_type: Optional[str] = None) -> int:
        with self._lock:
            if event_type is not None:
                return len(self._subscriptions.get(event_type, {}))
            return sum(len(subscribers) for subscribers in self._subscriptions.values())

    def close(self) -> None:
        with self._lock:
            self._subscriptions.clear()
