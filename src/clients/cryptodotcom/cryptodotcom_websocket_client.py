import time
from typing import Optional, Any, Callable

from api.interfaces.timeframe import Timeframe
from src.configuration.exchanges_config import ExchangesConfig
from src.core.interfaces.auth_handler import AuthHandler
from src.clients.cryptodotcom.handlers.auths.cryptodotcom_auth_handler import CryptoDotComAuthHandler
from src.clients.cryptodotcom.handlers.heartbeats.cryptodotcom_heartbeat_handler import CryptoDotComHeartbeatHandler
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.subscription_data import SubscriptionData, SubscriptionVisibility
from src.core.interfaces.exchange_websocket_client import ExchangeWebSocketClient
from src.clients.cryptodotcom.cryptodotcom_dto import CryptoDotComCandleResponseDto, \
    CryptoDotComMarketDataResponseDto, CryptoDotComResponseOrderUpdateDto, \
    CryptoDotComUserBalanceResponseDto
from src.clients.cryptodotcom.mappers.cryptodotcom_mapper import CryptoDotComMapper


class CryptoDotComWebSocketClient(ExchangeWebSocketClient):

    def __init__(self, config: ExchangesConfig = None):
        _config = config or ExchangesConfig()
        self._websocket_url = _config.crypto_dot_com.websocket_endpoint
        self._current_subscription: Optional[SubscriptionData] = None

    def market_data(self, ticker_symbol: str) -> 'CryptoDotComWebSocketClient':
        channel = f"ticker.{ticker_symbol}"
        self._current_subscription = self._build_sub(
            channel,
            SubscriptionVisibility.PUBLIC,
            lambda d: CryptoDotComMapper.to_marketdata(CryptoDotComMarketDataResponseDto(**d))
        )
        return self

    def candles(self, ticker_symbol: str, timeframe: Timeframe) -> 'CryptoDotComWebSocketClient':
        interval = CryptoDotComMapper.from_timeframe(timeframe)
        channel = f"candlestick.{interval}.{ticker_symbol}"
        self._current_subscription = self._build_sub(
            channel,
            SubscriptionVisibility.PUBLIC,
            lambda d: CryptoDotComMapper.to_candles(CryptoDotComCandleResponseDto(**d))
        )
        return self

    def account_balance(self) -> 'CryptoDotComWebSocketClient':
        self._current_subscription = self._build_sub(
            "user.balance",
            SubscriptionVisibility.PRIVATE,
            lambda d: CryptoDotComMapper.to_account_balance(CryptoDotComUserBalanceResponseDto(**d))
        )
        return self

    def order_update(self, instrument_name: str) -> 'CryptoDotComWebSocketClient':
        channel = f"user.order.{instrument_name}"
        self._current_subscription = self._build_sub(
            channel,
            SubscriptionVisibility.PRIVATE,
            lambda d: CryptoDotComMapper.to_orders(CryptoDotComResponseOrderUpdateDto(**d))
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

    def get_websocket_url(self, visibility: SubscriptionVisibility) -> str:
        endpoint = "user" if visibility is SubscriptionVisibility.PRIVATE else "market"
        return self._websocket_url + endpoint

    @staticmethod
    def get_provider_name() -> str:
        return "CRYPTO_DOT_COM"

    def get_auth_handler(self) -> Optional[AuthHandler]:
        return CryptoDotComAuthHandler()

    def get_heartbeat_handler(self) -> Optional[HeartbeatHandler]:
        return CryptoDotComHeartbeatHandler()
