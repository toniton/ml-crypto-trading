from typing import Optional

from src.configuration.providers.cryptodotcom_config import CryptodotcomConfig
from src.core.interfaces.auth_handler import AuthHandler
from src.subscriptions.handlers.auths.cryptodotcom_auth_handler import CryptoDotComAuthHandler
from src.subscriptions.heartbeats.cryptodotcom_heartbeat_handler import CryptoDotComHeartbeatHandler
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.subscription_data import BalanceSubscriptionData, \
    MarketDataSubscriptionData, OrderCreatedSubscriptionData, \
    OrderUpdateSubscriptionData, SubscriptionVisibility
from src.core.interfaces.exchange_websocket_client import ExchangeWebSocketClient
from src.trading.helpers.trading_helper import TradingHelper
from src.trading.providers.cryptodotcom_dto import CryptoDotComMarketDataResponseDto, CryptoDotComUserBalanceResponseDto
from src.trading.providers.mappers.cryptodotcom_mapper import CryptoDotComMapper


class CryptoDotComWebSocketClient(ExchangeWebSocketClient):

    def __init__(self, config: CryptodotcomConfig = None):
        super().__init__()
        self.config = config or CryptodotcomConfig.get_instance()

    def _get_websocket_url(self, visibility: SubscriptionVisibility) -> str:
        if visibility is SubscriptionVisibility.PRIVATE:
            return self.config.websocket_url + "user"
        return self.config.websocket_url + "market"

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

    def _get_order_created_subscription(self) -> OrderCreatedSubscriptionData:
        """Order created subscription includes auth payload."""
        return OrderCreatedSubscriptionData(
            subscribe_payload={
                "id": 1,
                "method": "subscribe",
                "params": {"channels": ["order"]}
            },
            unsubscribe_payload={
                "id": 1,
                "method": "unsubscribe",
                "params": {"channels": ["order"]}
            }
        )

    def _get_order_update_subscription(self, order_id: str) -> OrderUpdateSubscriptionData:
        """Order update subscription includes auth payload."""
        return OrderUpdateSubscriptionData(
            subscribe_payload={
                "id": 1,
                "method": "subscribe",
                "params": {"channels": [f"order.{order_id}"]}
            },
            unsubscribe_payload={
                "id": 1,
                "method": "unsubscribe",
                "params": {"channels": [f"order.{order_id}"]}
            },
            parser=lambda data: data
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
