from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.interfaces.event import Event
from src.core.interfaces.event_subscription import EventSubscription


class EventBus(ABC):
    @abstractmethod
    def subscribe(self, event_type: str, subscription: EventSubscription) -> str:
        raise NotImplementedError()

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> None:
        raise NotImplementedError()

    @abstractmethod
    def publish(self, event: Event) -> None:
        raise NotImplementedError()

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError()
