from abc import ABC, abstractmethod
from typing import Callable, Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from src.core.interfaces.auth_handler import AuthHandler
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.subscription_data import BalanceSubscriptionData, \
    MarketDataSubscriptionData, \
    OrderUpdateSubscriptionData, SubscriptionData, SubscriptionVisibility
from src.core.managers.websocket_manager import WebSocketManager


class ExchangeWebSocketClient(ABC):
    def __init__(self):
        self._ws_manager: Optional[WebSocketManager] = None

    @abstractmethod
    def _get_websocket_url(self, visibility: SubscriptionVisibility) -> str:
        pass

    @abstractmethod
    def _get_auth_handler(self) -> AuthHandler:
        pass

    @staticmethod
    @abstractmethod
    def get_provider_name() -> str:
        pass

    @abstractmethod
    def _get_balance_subscription(self) -> BalanceSubscriptionData:
        pass

    @abstractmethod
    def _get_order_update_subscription(self, instrument_name: str) -> OrderUpdateSubscriptionData:
        pass

    @abstractmethod
    def _get_market_data_subscription(self, ticker_symbol: str) -> MarketDataSubscriptionData:
        pass

    @abstractmethod
    def _get_heartbeat_handler(self) -> Optional[HeartbeatHandler]:
        pass

    def subscribe_balance(self, callback: Callable[[list[AccountBalance]], None]) -> str:
        sub_data = self._get_balance_subscription()
        return self._subscribe(
            connection_key=f"{self.get_provider_name()}-BALANCE",
            subscription_data=sub_data,
            callback=lambda key, data: callback(sub_data.parse(data))
        )

    def subscribe_order_update(self, instrument_name: str, callback: Callable[[list[Order]], None]) -> str:
        sub_data = self._get_order_update_subscription(instrument_name)
        return self._subscribe(
            connection_key=f"{self.get_provider_name()}-ORDER_{instrument_name}",
            subscription_data=sub_data,
            callback=lambda key, data: callback(sub_data.parse(data))
        )

    def subscribe_market_data(self, ticker_symbol: str, callback: Callable[[str, MarketData], None]) -> str:
        sub_data = self._get_market_data_subscription(ticker_symbol)
        return self._subscribe(
            connection_key=f"{self.get_provider_name()}-MARKET_{ticker_symbol}",
            subscription_data=sub_data,
            callback=lambda key, data: callback(key, sub_data.parse(data))
        )

    def unsubscribe(self, connection_key: str) -> None:
        if self._ws_manager:
            self._ws_manager.unsubscribe(connection_key)

    def _get_ws_manager(self) -> WebSocketManager:
        if self._ws_manager is None:
            self._ws_manager = WebSocketManager(provider_name=self.get_provider_name(),
                                                get_websocket_url=self._get_websocket_url,
                                                auth_handler=self._get_auth_handler(),
                                                heartbeat_handler=self._get_heartbeat_handler())
        return self._ws_manager

    def _subscribe(
            self,
            connection_key: str,
            subscription_data: SubscriptionData,
            callback: Callable
    ) -> str:
        ws_manager = self._get_ws_manager()
        return ws_manager.subscribe(
            connection_key=connection_key,
            subscription_data=subscription_data,
            callback=callback
        )
