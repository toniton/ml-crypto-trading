from typing import Optional

from src.clients.cryptodotcom.cryptodotcom_websocket_builder import CryptoDotComWebSocketBuilder
from src.clients.cryptodotcom.handlers.auths.cryptodotcom_auth_handler import CryptoDotComAuthHandler
from src.clients.cryptodotcom.handlers.heartbeats.cryptodotcom_heartbeat_handler import CryptoDotComHeartbeatHandler
from src.configuration.exchanges_config import ExchangesConfig
from src.core.interfaces.exchange_rest_client import ExchangeProvidersEnum
from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.auth_handler import AuthHandler
from src.core.interfaces.subscription_data import SubscriptionVisibility


class CryptoDotComWebSocketService(ExchangeWebSocketService):

    def __init__(self):
        config = ExchangesConfig()
        self._websocket_url = config.crypto_dot_com.websocket_endpoint

    def get_provider_name(self) -> str:
        return ExchangeProvidersEnum.CRYPTO_DOT_COM.name

    def get_websocket_url(self, visibility: SubscriptionVisibility) -> str:
        endpoint = "user" if visibility is SubscriptionVisibility.PRIVATE else "market"
        return self._websocket_url + endpoint

    def get_auth_request(self) -> dict:
        return CryptoDotComAuthHandler().get_auth_request()

    def get_auth_handler(self) -> Optional[AuthHandler]:
        return CryptoDotComAuthHandler()

    def get_heartbeat_handler(self) -> Optional[HeartbeatHandler]:
        return CryptoDotComHeartbeatHandler()

    def create_builder(self) -> ExchangeWebSocketBuilder:
        return CryptoDotComWebSocketBuilder()
