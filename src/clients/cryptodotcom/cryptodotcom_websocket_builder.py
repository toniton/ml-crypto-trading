import time
from typing import Optional, Any, Callable

from api.interfaces.timeframe import Timeframe
from src.clients.cryptodotcom.mappers.cryptodotcom_mappers import (
    CryptoDotComMarketDataMapper,
    CryptoDotComCandleMapper,
    CryptoDotComAccountBalanceMapper,
    CryptoDotComOrdersMapper
)
from src.clients.cryptodotcom.utils.timeframe_map import CryptoDotComTimeframe
from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.subscription_data import SubscriptionData, SubscriptionVisibility


class CryptoDotComWebSocketBuilder(ExchangeWebSocketBuilder):

    def __init__(self):
        super().__init__()
        self._current_subscription: Optional[SubscriptionData] = None

    def market_data(self, ticker_symbol: str) -> 'CryptoDotComWebSocketBuilder':
        channel = f"ticker.{ticker_symbol}"
        mapper = CryptoDotComMarketDataMapper()
        self._current_subscription = self._build_sub(
            channel,
            SubscriptionVisibility.PUBLIC,
            mapper.map
        )
        return self

    def candles(self, ticker_symbol: str, timeframe: Timeframe) -> 'CryptoDotComWebSocketBuilder':
        interval = CryptoDotComTimeframe.MAP.get(timeframe)
        channel = f"candlestick.{interval}.{ticker_symbol}"
        mapper = CryptoDotComCandleMapper()
        self._current_subscription = self._build_sub(
            channel,
            SubscriptionVisibility.PUBLIC,
            mapper.map
        )
        return self

    def account_balance(self) -> 'CryptoDotComWebSocketBuilder':
        mapper = CryptoDotComAccountBalanceMapper()
        self._current_subscription = self._build_sub(
            "user.balance",
            SubscriptionVisibility.PRIVATE,
            mapper.map
        )
        return self

    def order_update(self, instrument_name: str) -> 'CryptoDotComWebSocketBuilder':
        channel = f"user.order.{instrument_name}"
        mapper = CryptoDotComOrdersMapper()
        self._current_subscription = self._build_sub(
            channel,
            SubscriptionVisibility.PRIVATE,
            mapper.map
        )
        return self

    def get_subscription_data(self) -> SubscriptionData:
        if not self._current_subscription:
            raise ValueError("No subscription configured")
        return self._current_subscription

    @staticmethod
    def _build_sub(channel: str, visibility: SubscriptionVisibility, parser: Callable) -> SubscriptionData:
        return SubscriptionData(
            payload={
                "id": time.time_ns(),
                "method": "subscribe",
                "params": {"channels": [channel]}
            },
            visibility=visibility,
            parser=parser,
            filter=lambda d: d.get("result", {}).get("subscription") == channel
        )

    def get_unsubscribe_payload(self, subscribe_payload: dict[str, Any]) -> dict[str, Any]:
        payload = subscribe_payload.copy()
        payload["id"] = time.time_ns()
        payload["method"] = "unsubscribe"
        return payload
