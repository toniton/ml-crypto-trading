from __future__ import annotations

from typing import Callable

from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.subscription_data import SubscriptionVisibility
from src.exchange.managers.websocket_manager import WebSocketManager


class SimulatedWebSocketManager(WebSocketManager):
    def _subscribe(
            self, key: str, service: ExchangeWebSocketService,
            builder: ExchangeWebSocketBuilder, callback: Callable
    ):
        sub_data = builder.get_subscription_data()
        if sub_data.visibility == SubscriptionVisibility.PRIVATE:
            exchange = service.get_provider_name()
            self.app_logger.info(f"Simulated mode: Skipping private subscription for {key} on {exchange}")
            with self._lock:
                self._subscriptions[exchange][key] = (builder, callback)
            return

        super()._subscribe(key, service, builder, callback)
