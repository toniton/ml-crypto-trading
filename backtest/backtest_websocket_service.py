from __future__ import annotations
from typing import Optional

from backtest.backtest_event_bus import BacktestEventBus
from backtest.backtest_websocket_builder import BacktestWebSocketBuilder
from src.core.interfaces.auth_handler import AuthHandler
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.subscription_data import SubscriptionVisibility
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService


class BacktestWebSocketService(ExchangeWebSocketService):
    def __init__(self, event_bus: BacktestEventBus):
        self.bus = event_bus

    def get_provider_name(self) -> str:
        return "CRYPTO_DOT_COM"

    def get_websocket_url(self, visibility: SubscriptionVisibility) -> str:
        return "backtest://event-bus"

    def get_auth_request(self) -> dict:
        return {}

    def get_auth_handler(self) -> Optional[AuthHandler]:
        return None

    def get_heartbeat_handler(self) -> Optional[HeartbeatHandler]:
        return None

    def create_builder(self) -> BacktestWebSocketBuilder:
        return BacktestWebSocketBuilder(self.bus)
