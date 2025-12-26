from typing import Optional

from src.configuration.exchanges_config import ExchangesConfig
from src.core.interfaces.auth_handler import AuthHandler
from src.clients.cryptodotcom.handlers.auths.cryptodotcom_auth_handler import CryptoDotComAuthHandler
from src.clients.cryptodotcom.handlers.heartbeats.cryptodotcom_heartbeat_handler import CryptoDotComHeartbeatHandler
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.subscription_data import BalanceSubscriptionData, \
    MarketDataSubscriptionData, \
    OrderUpdateSubscriptionData, SubscriptionVisibility
from src.core.interfaces.exchange_websocket_client import ExchangeWebSocketClient
from src.trading.helpers.trading_helper import TradingHelper
from src.clients.cryptodotcom.cryptodotcom_dto import CryptoDotComMarketDataResponseDto, \
    CryptoDotComResponseOrderUpdateDto, CryptoDotComUserBalanceResponseDto
from src.clients.cryptodotcom.mappers.cryptodotcom_mapper import CryptoDotComMapper


class CryptoDotComWebSocketClient(ExchangeWebSocketClient):

    def __init__(self, config: ExchangesConfig = None):
        super().__init__()
        _config = config or ExchangesConfig()
        self._websocket_url = _config.crypto_dot_com.websocket_endpoint

    def _get_websocket_url(self, visibility: SubscriptionVisibility) -> str:
        if visibility is SubscriptionVisibility.PRIVATE:
            return self._websocket_url + "user"
        return self._websocket_url + "market"

    @staticmethod
    def get_provider_name() -> str:
        return "CRYPTO_DOT_COM"

    def _get_auth_handler(self) -> AuthHandler:
        return CryptoDotComAuthHandler()

    def _get_balance_subscription(self) -> BalanceSubscriptionData:
        return BalanceSubscriptionData(
            subscribe_payload={
                "id": 1,
                "method": "subscribe",
                "params": {"channels": ["user.balance"]}
            },
            unsubscribe_payload={
                "id": 1,
                "method": "unsubscribe",
                "params": {"channels": ["user.balance"]}
            },
            parser=lambda data: CryptoDotComMapper.to_account_balance(CryptoDotComUserBalanceResponseDto(**data))
        )

    def _get_order_update_subscription(self, instrument_name: str) -> OrderUpdateSubscriptionData:
        return OrderUpdateSubscriptionData(
            subscribe_payload={
                "id": 1,
                "method": "subscribe",
                "params": {"channels": [f"user.order.{instrument_name}"]}
            },
            unsubscribe_payload={
                "id": 1,
                "method": "unsubscribe",
                "params": {"channels": [f"user.order.{instrument_name}"]}
            },
            parser=lambda data: CryptoDotComMapper.to_orders(CryptoDotComResponseOrderUpdateDto(**data))
        )

    def _get_market_data_subscription(self, ticker_symbol: str) -> MarketDataSubscriptionData:
        ticker = TradingHelper.format_ticker_symbol(ticker_symbol, suffix="-PERP")
        return MarketDataSubscriptionData(
            subscribe_payload={
                "id": 1,
                "method": "subscribe",
                "params": {"channels": [f"ticker.{ticker}"]}
            },
            unsubscribe_payload={
                "id": 1,
                "method": "unsubscribe",
                "params": {"channels": [f"ticker.{ticker}"]}
            },
            parser=lambda data: CryptoDotComMapper.to_marketdata(CryptoDotComMarketDataResponseDto(**data))
        )

    def _get_heartbeat_handler(self) -> Optional[HeartbeatHandler]:
        return CryptoDotComHeartbeatHandler()
