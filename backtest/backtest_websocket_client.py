from typing import Callable, Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from backtest.backtest_event_bus import BacktestEventBus
from backtest.events import MarketDataEvent, OrderFillEvent, BalanceUpdateEvent, Event
from src.core.interfaces.auth_handler import AuthHandler
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.subscription_data import (
    BalanceSubscriptionData,
    MarketDataSubscriptionData,
    OrderUpdateSubscriptionData,
    SubscriptionVisibility,
)
from src.core.interfaces.exchange_websocket_client import ExchangeWebSocketClient


class BacktestAuthHandler(AuthHandler):
    def is_auth_response(self, message: dict) -> bool:
        pass

    def get_auth_request(self) -> Optional[dict]:
        pass

    def handle_auth_response(self, message: dict) -> int:
        pass


class BacktestWebSocketClient(ExchangeWebSocketClient):
    def __init__(self, event_bus: BacktestEventBus):
        super().__init__()
        self.bus = event_bus
        self._subscription_ids: dict[str, int] = {}

    def _get_websocket_url(self, visibility: SubscriptionVisibility) -> str:
        return "backtest://event-bus"

    @staticmethod
    def get_provider_name() -> str:
        return "CRYPTO_DOT_COM"

    def _get_auth_handler(self) -> AuthHandler:
        return BacktestAuthHandler()

    def _get_balance_subscription(self) -> BalanceSubscriptionData:
        return BalanceSubscriptionData({}, {}, lambda d: [])

    def _get_order_update_subscription(self, instrument_name: str) -> OrderUpdateSubscriptionData:
        return OrderUpdateSubscriptionData({}, {}, lambda d: [])

    def _get_market_data_subscription(self, ticker_symbol: str) -> MarketDataSubscriptionData:
        return MarketDataSubscriptionData({}, {}, lambda d: None)

    def _get_heartbeat_handler(self) -> Optional[HeartbeatHandler]:
        return None

    def subscribe_balance(self, callback: Callable[[list[AccountBalance]], None]) -> str:
        connection_key = f"{self.get_provider_name()}-BALANCE"

        def _handler(event: Event):
            if isinstance(event, BalanceUpdateEvent):
                callback(event.balances)

        sub_id = self.bus.subscribe(BalanceUpdateEvent, _handler)
        self._subscription_ids[connection_key] = sub_id
        return connection_key

    def subscribe_order_update(
            self, instrument_name: str, callback: Callable[[list[Order]], None]
    ) -> str:
        connection_key = f"{self.get_provider_name()}-ORDER_{instrument_name}"

        def _handler(event: Event):
            if isinstance(event, OrderFillEvent):
                if event.order.ticker_symbol == instrument_name:
                    callback([event.order])

        sub_id = self.bus.subscribe(OrderFillEvent, _handler)
        self._subscription_ids[connection_key] = sub_id
        return connection_key

    def subscribe_market_data(
            self, ticker_symbol: str, callback: Callable[[str, MarketData], None]
    ) -> str:
        connection_key = f"{self.get_provider_name()}-MARKET_{ticker_symbol}"

        def _handler(event: Event):
            if isinstance(event, MarketDataEvent):
                if event.ticker_symbol == ticker_symbol:
                    callback(connection_key, event.market_data)

        sub_id = self.bus.subscribe(MarketDataEvent, _handler)
        self._subscription_ids[connection_key] = sub_id
        return connection_key

    def unsubscribe(self, connection_key: str) -> None:
        if connection_key in self._subscription_ids:
            sub_id = self._subscription_ids[connection_key]
            self.bus.unsubscribe(sub_id)
            del self._subscription_ids[connection_key]

    def _subscribe(self, connection_key: str, subscription_data, callback: Callable) -> str:
        return connection_key
