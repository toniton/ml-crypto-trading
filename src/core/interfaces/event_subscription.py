from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.interfaces.event import Event


class EventSubscription(ABC):
    @abstractmethod
    def put(self, event: Event) -> None:
        raise NotImplementedError()

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError()
