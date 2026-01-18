from abc import ABC, abstractmethod

from api.interfaces.timeframe import Timeframe
from src.core.interfaces.subscription_data import SubscriptionData


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
