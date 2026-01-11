from abc import ABC, abstractmethod
from typing import Optional

from api.interfaces.timeframe import Timeframe
from src.core.interfaces.auth_handler import AuthHandler
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.subscription_data import SubscriptionData, SubscriptionVisibility


class ExchangeWebSocketBuilder(ABC):

    @abstractmethod
    def market_data(self, ticker_symbol: str) -> 'ExchangeWebSocketBuilder':
        pass

    @abstractmethod
    def candles(self, ticker_symbol: str, timeframe: Timeframe) -> 'ExchangeWebSocketBuilder':
        pass

    @abstractmethod
    def account_balance(self) -> 'ExchangeWebSocketBuilder':
        pass

    @abstractmethod
    def order_update(self, instrument_name: str) -> 'ExchangeWebSocketBuilder':
        pass

    @abstractmethod
    def get_subscription_data(self) -> SubscriptionData:
        pass

    @abstractmethod
    def get_unsubscribe_payload(self, subscribe_payload: dict) -> dict:
        pass

    @abstractmethod
    def get_websocket_url(self, visibility: SubscriptionVisibility) -> str:
        pass

    @abstractmethod
    def get_auth_handler(self) -> Optional[AuthHandler]:
        pass

    @abstractmethod
    def get_heartbeat_handler(self) -> Optional[HeartbeatHandler]:
        pass

    @staticmethod
    @abstractmethod
    def get_provider_name() -> str:
        pass
