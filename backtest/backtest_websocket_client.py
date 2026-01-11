from typing import Optional, Any

from api.interfaces.timeframe import Timeframe
from backtest.backtest_event_bus import BacktestEventBus
from src.core.interfaces.auth_handler import AuthHandler
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.subscription_data import (
    SubscriptionData,
    SubscriptionVisibility,
)
from src.core.interfaces.exchange_websocket_client import ExchangeWebSocketClient


class BacktestAuthHandler(AuthHandler):
    def is_auth_response(self, message: dict) -> bool:
        return False

    def get_auth_request(self) -> Optional[dict]:
        return None

    def handle_auth_response(self, message: dict) -> None:
        pass


class BacktestWebSocketClient(ExchangeWebSocketClient):
    def __init__(self, event_bus: BacktestEventBus):
        self.bus = event_bus
        self._current_subscription: Optional[dict[str, Any]] = None

    def market_data(self, ticker_symbol: str) -> 'BacktestWebSocketClient':
        self._current_subscription = {"type": "market_data", "ticker_symbol": ticker_symbol}
        return self

    def candles(self, ticker_symbol: str, timeframe: Timeframe) -> 'BacktestWebSocketClient':
        self._current_subscription = {"type": "candles", "ticker_symbol": ticker_symbol, "timeframe": timeframe}
        return self

    def account_balance(self) -> 'BacktestWebSocketClient':
        self._current_subscription = {"type": "balance"}
        return self

    def order_update(self, instrument_name: str) -> 'BacktestWebSocketClient':
        self._current_subscription = {"type": "order_update", "instrument_name": instrument_name}
        return self

    def get_subscription_data(self) -> SubscriptionData:
        if not self._current_subscription:
            raise ValueError("No subscription configured")

        sub_type = self._current_subscription["type"]
        visibility = SubscriptionVisibility.PUBLIC \
            if sub_type in ["market_data", "candles"] else SubscriptionVisibility.PRIVATE

        if sub_type == "market_data":
            ticker_symbol = self._current_subscription["ticker_symbol"]
            return SubscriptionData(
                payload={"type": sub_type, "params": self._current_subscription},
                visibility=visibility,
                parser=lambda d: d["data"],
                filter=lambda d: d.get("type") == "market_data" and d.get("ticker_symbol") == ticker_symbol
            )
        if sub_type == "candles":
            ticker_symbol = self._current_subscription["ticker_symbol"]
            return SubscriptionData(
                payload={"type": sub_type, "params": self._current_subscription},
                visibility=visibility,
                parser=lambda d: d["data"],
                filter=lambda d: d.get("type") == "candles" and d.get("ticker_symbol") == ticker_symbol
            )
        if sub_type == "balance":
            return SubscriptionData(
                payload={"type": sub_type, "params": self._current_subscription},
                visibility=visibility,
                parser=lambda d: d["data"],
                filter=lambda d: d.get("type") == "balance"
            )
        if sub_type == "order_update":
            instrument_name = self._current_subscription["instrument_name"]
            return SubscriptionData(
                payload={"type": sub_type, "params": self._current_subscription},
                visibility=visibility,
                parser=lambda d: d["data"],
                filter=lambda d: d.get("type") == "order_update" and d.get("instrument_name") == instrument_name
            )

        raise ValueError(f"Unknown subscription type: {sub_type}")

    def get_unsubscribe_payload(self, subscribe_payload: dict) -> dict:
        payload = subscribe_payload.copy()
        payload["method"] = "unsubscribe"
        return payload

    def get_websocket_url(self, visibility: SubscriptionVisibility) -> str:
        return "backtest://event-bus"

    @staticmethod
    def get_provider_name() -> str:
        return "CRYPTO_DOT_COM"

    def get_auth_handler(self) -> Optional[AuthHandler]:
        return BacktestAuthHandler()

    def get_heartbeat_handler(self) -> Optional[HeartbeatHandler]:
        return None
