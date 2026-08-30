from __future__ import annotations

from typing import Any, Optional

from api.interfaces.timeframe import Timeframe
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.events.domain_events import (
    BalanceUpdateEvent,
    CandlesEvent,
    BacktestEvent,
    MarketDataEvent,
    OrderFillEvent,
)
from src.core.interfaces.auth_handler import AuthHandler
from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.subscription_data import (
    SubscriptionData,
    SubscriptionVisibility,
)


class BacktestAuthHandler(AuthHandler):
    def is_auth_response(self, message: dict) -> bool:
        return False

    def get_auth_request(self) -> Optional[dict]:
        return None

    def handle_auth_response(self, message: dict) -> None:
        pass


class BacktestWebSocketBuilder(ExchangeWebSocketBuilder):
    def __init__(self, event_bus: BacktestEventBus):
        self.bus = event_bus
        self._current_subscription: Optional[dict[str, Any]] = None

    def market_data(self, ticker_symbol: str) -> 'BacktestWebSocketBuilder':
        self._current_subscription = {
            "type": "market_data",
            "ticker_symbol": ticker_symbol,
            "event_class": MarketDataEvent
        }
        return self

    def candles(self, ticker_symbol: str, timeframe: Timeframe) -> 'BacktestWebSocketBuilder':
        self._current_subscription = {
            "type": "candles",
            "ticker_symbol": ticker_symbol,
            "timeframe": timeframe.value,
            "event_class": CandlesEvent
        }
        return self

    def account_balance(self) -> 'BacktestWebSocketBuilder':
        self._current_subscription = {
            "type": "balance",
            "event_class": BalanceUpdateEvent
        }
        return self

    def order_update(self, instrument_name: str) -> 'BacktestWebSocketBuilder':
        self._current_subscription = {
            "type": "order_update",
            "instrument_name": instrument_name,
            "event_class": OrderFillEvent
        }
        return self

    @property
    def event_class(self) -> type[BacktestEvent] | None:
        if not self._current_subscription:
            return None
        return self._current_subscription.get("event_class")

    @property
    def key(self) -> str | None:
        if not self._current_subscription:
            return None
        sub_type = self._current_subscription["type"]
        if sub_type == "market_data":
            return f"MARKET_{self._current_subscription['ticker_symbol']}"
        if sub_type == "candles":
            return (f"CANDLES_{self._current_subscription['ticker_symbol']}"
                    f"_{self._current_subscription['timeframe']}")
        if sub_type == "balance":
            return "BALANCE"
        if sub_type == "order_update":
            return f"ORDER_{self._current_subscription['instrument_name']}"
        return sub_type

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
