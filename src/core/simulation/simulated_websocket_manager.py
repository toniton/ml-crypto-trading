from __future__ import annotations

from typing import Callable

from src.clients.websocket_manager import WebSocketManager
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.subscription_data import SubscriptionData, SubscriptionVisibility


class SimulatedWebSocketManager(WebSocketManager):
    def _ensure_connection(self, service: ExchangeWebSocketService, visibility: SubscriptionVisibility):
        if visibility == SubscriptionVisibility.PRIVATE:
            exchange = service.get_provider_name()
            conn_id = f"{exchange}-{visibility.value}"
            self.app_logger.info(f"Simulated mode: Skipping private WebSocket connection for {conn_id}")
            return

        super()._ensure_connection(service, visibility)

    def _subscribe(self, exchange: str, key: str, sub_data: SubscriptionData, callback: Callable):
        if sub_data.visibility == SubscriptionVisibility.PRIVATE:
            self.app_logger.info(f"Simulated mode: Skipping private subscription for {key} on {exchange}")
            with self._lock:
                self._subscriptions[exchange][key] = (sub_data, callback)
            return

        super()._subscribe(exchange, key, sub_data, callback)
