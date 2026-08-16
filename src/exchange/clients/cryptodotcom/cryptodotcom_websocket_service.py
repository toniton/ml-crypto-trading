from __future__ import annotations

import json
import threading
import time
from typing import Callable, ClassVar, Optional
from websocket import WebSocketApp

from src.configuration.exchanges_config import ExchangesConfig
from src.core.interfaces.auth_handler import AuthHandler
from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.subscription_data import SubscriptionVisibility
from src.exchange.clients.cryptodotcom.cryptodotcom_websocket_builder import CryptoDotComWebSocketBuilder
from src.exchange.clients.cryptodotcom.handlers.auths.cryptodotcom_auth_handler import CryptoDotComAuthHandler
from src.exchange.clients.cryptodotcom.handlers.heartbeats.cryptodotcom_heartbeat_handler import \
    CryptoDotComHeartbeatHandler
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class CryptoDotComWebSocketService(ExchangeWebSocketService, ApplicationLoggingMixin):
    _SUPPORTED_PROVIDERS: ClassVar[set[str]] = {ExchangeProvidersEnum.CRYPTO_DOT_COM.name.lower()}

    def __init__(self, provider: str = None):
        config = ExchangesConfig()
        self._provider = provider or ExchangeProvidersEnum.CRYPTO_DOT_COM.name.lower()
        self._websocket_url = config.crypto_dot_com.websocket_endpoint
        self._lock = threading.Lock()
        self._connections: dict[str, dict[SubscriptionVisibility, WebSocketApp | None]] = {}
        self._authenticated_connections: set[str] = set()
        self._last_heartbeat: dict[str, float] = {}
        self._callback: Optional[Callable] = None
        self._connection_events: dict[str, threading.Event] = {}

    @classmethod
    def get_supported_providers(cls) -> set[str]:
        return cls._SUPPORTED_PROVIDERS

    def get_provider_name(self) -> str:
        return self._provider.upper()

    def get_websocket_url(self, visibility: SubscriptionVisibility) -> str:
        endpoint = "user" if visibility is SubscriptionVisibility.PRIVATE else "market"
        return self._websocket_url + endpoint

    def get_auth_request(self) -> dict:
        return CryptoDotComAuthHandler().get_auth_request()

    def get_auth_handler(self) -> Optional[AuthHandler]:
        return CryptoDotComAuthHandler()

    def get_heartbeat_handler(self) -> Optional[HeartbeatHandler]:
        return CryptoDotComHeartbeatHandler()

    def builder(self) -> ExchangeWebSocketBuilder:
        return CryptoDotComWebSocketBuilder()

    def connect(self, callback: Callable):
        self._callback = callback
        provider_name = self.get_provider_name()
        if provider_name not in self._connections:
            self._connections[provider_name] = {}

        self._ensure_connection(self, SubscriptionVisibility.PUBLIC)
        self._ensure_connection(self, SubscriptionVisibility.PRIVATE)

    def _ensure_connection(
            self, service: ExchangeWebSocketService,
            visibility: SubscriptionVisibility
    ):
        exchange = service.get_provider_name()
        with self._lock:
            if visibility in self._connections[exchange]:
                return

        url = service.get_websocket_url(visibility)
        conn_id = f"{exchange}-{visibility.value}"
        self._connection_events[conn_id] = threading.Event()

        handler = WebSocketApp(
            url=url,
            on_open=lambda ws: self._handle_open(exchange, visibility),
            on_message=lambda ws, data: self._handle_message(exchange, visibility, data),
            on_error=lambda ws, e: self.app_logger.error(f"WebSocket error for {conn_id}: {e}"),
            on_close=lambda ws, code, msg: self._handle_close(exchange, visibility, code, msg)
        )

        with self._lock:
            if visibility not in self._connections[exchange]:
                self._connections[exchange][visibility] = handler

        thread = threading.Thread(
            target=handler.run_forever,
            daemon=True,
            name=f"WS-{conn_id}"
        )
        thread.start()
        self.app_logger.info(f"Started WebSocket connection for {conn_id}")

        # Wait for connection to be established
        if not self._connection_events[conn_id].wait(timeout=10):
            self.app_logger.warning(f"Timeout waiting for WebSocket connection {conn_id}")

    def _handle_open(self, exchange: str, visibility: SubscriptionVisibility):
        conn_id = f"{exchange}-{visibility.value}"
        self.app_logger.info(f"WebSocket connected for {conn_id}")
        self._connection_events[conn_id].set()

        if visibility == SubscriptionVisibility.PRIVATE:
            handler = self._connections[exchange][visibility]
            auth_request = self.get_auth_request()
            if auth_request:
                handler.send(json.dumps(auth_request))
                self._authenticated_connections.add(conn_id)
                self.app_logger.info(f"Sent auth request for {conn_id}")

    def subscribe(self, builder: ExchangeWebSocketBuilder):
        sub_data = builder.get_subscription_data()
        key = builder.key
        exchange = self.get_provider_name()
        self._ensure_connection(self, sub_data.visibility)

        # Ensure connection is ready before sending
        conn_id = f"{exchange}-{sub_data.visibility.value}"
        self._connection_events[conn_id].wait()

        with self._lock:
            handler = self._connections[exchange][sub_data.visibility]
            handler.send(json.dumps(sub_data.payload))
            self.app_logger.info(f"Subscribed to {key} on {exchange}")

    def _handle_message(self, exchange: str, visibility: SubscriptionVisibility, message: str):
        try:
            data = json.loads(message)
            self.inject_message(exchange, visibility, data)
        except Exception as e:
            self.app_logger.error(f"Error handling message from {exchange}: {e}", exc_info=True)

    def inject_message(self, exchange: str, visibility: SubscriptionVisibility, data: dict):
        # Auth handling
        auth_handler = self.get_auth_handler()
        if auth_handler and auth_handler.is_auth_response(data):
            auth_handler.handle_auth_response(data)
            return

        # Heartbeat handling
        heartbeat_handler = self.get_heartbeat_handler()
        if heartbeat_handler and heartbeat_handler.is_heartbeat(data):
            conn_id = f"{exchange}-{visibility.value}"
            with self._lock:
                self._last_heartbeat[conn_id] = time.time()
                handler = self._connections.get(exchange, {}).get(visibility)

            response = heartbeat_handler.get_heartbeat_response(data)
            if response and handler:
                handler.send(json.dumps(response))
            return

        # Pass everything else to the central manager
        if self._callback:
            self._callback(exchange, visibility, data)

    def _handle_close(self, exchange: str, visibility: SubscriptionVisibility, code: int, msg: str):
        conn_id = f"{exchange}-{visibility.value}"
        self.app_logger.info(f"WebSocket closed for {conn_id}. Code: {code}, Msg: {msg}")

        with self._lock:
            if conn_id in self._authenticated_connections:
                self._authenticated_connections.remove(conn_id)

            if exchange in self._connections:
                self._connections[exchange].pop(visibility, None)

        # Immediate reconnect logic could go here, or handled by a supervisor.
        if code != 1000:
            self.app_logger.warning(f"Abnormal closure for {conn_id}, attempting to reconnect...")
            # Re-establishing connection will happen on next subscribe, or we can trigger it here.
            # For simplicity, we just clear it so next use reconnects.

    def unsubscribe(self, builder: ExchangeWebSocketBuilder):
        exchange = self.get_provider_name()
        sub_data = builder.get_subscription_data()
        key = builder.key
        with self._lock:
            handler = self._connections[exchange].get(sub_data.visibility)
            if handler is None:
                self.app_logger.warning(
                    f"Cannot unsubscribe from {key}: no active connection for {exchange}-{sub_data.visibility.value}"
                )
                return
            unsub_payload = builder.get_unsubscribe_payload(sub_data.payload)
            handler.send(json.dumps(unsub_payload))

        self.app_logger.info(f"Unsubscribed from {key} on {exchange}")
