from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from src.core.interfaces.auth_handler import AuthHandler
from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.subscription_data import SubscriptionVisibility


class ExchangeWebSocketService(ABC):

    @abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abstractmethod
    def get_websocket_url(self, visibility: SubscriptionVisibility) -> str:
        pass

    @abstractmethod
    def get_auth_request(self) -> dict:
        pass

    @abstractmethod
    def get_auth_handler(self) -> Optional[AuthHandler]:
        pass

    @abstractmethod
    def get_heartbeat_handler(self) -> Optional[HeartbeatHandler]:
        pass

    @abstractmethod
    def builder(self) -> ExchangeWebSocketBuilder:
        pass

    @abstractmethod
    def connect(self, callback: Callable):
        pass

    @abstractmethod
    def subscribe(self, builder: ExchangeWebSocketBuilder):
        pass

    @abstractmethod
    def unsubscribe(self, builder: ExchangeWebSocketBuilder):
        pass
