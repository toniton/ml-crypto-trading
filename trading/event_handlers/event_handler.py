import abc
from abc import ABC
from typing import Any


class EventHandler(ABC):
    @abc.abstractmethod
    def on_handle_event(self, data: Any):
        pass
