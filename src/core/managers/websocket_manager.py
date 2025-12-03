import json
import logging
import threading
import time
from typing import Callable, Optional

from websocket import WebSocketApp

from src.core.interfaces.auth_handler import AuthHandler
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.subscription_data import SubscriptionData, SubscriptionVisibility


class WebSocketManager:

    def __init__(
            # TODO: get_websocket_url cannot be a function, function calls are expensive.
            self, provider_name: str, get_websocket_url: Callable[[SubscriptionVisibility], str],
            auth_handler: Optional[AuthHandler] = None, heartbeat_handler: Optional[HeartbeatHandler] = None
    ):
        self.get_websocket_url = get_websocket_url
        self.provider_name = provider_name
        self.auth_handler = auth_handler
        self.heartbeat_handler = heartbeat_handler
        self.subscriptions: dict[str, tuple[SubscriptionData, Callable]] = {}
        self.connections: dict[str, WebSocketApp] = {}
        self.authenticated_connections: set[str] = set()
        self.last_heartbeat: dict[str, float] = {}

    def subscribe(
            self, connection_key: str,
            subscription_data: SubscriptionData,
            callback: Callable, **sub_kwargs
    ) -> str:
        if connection_key in self.connections:
            handler = self.connections[connection_key]
            logging.info(f"Reusing existing handler for {connection_key} on {self.provider_name}")
            handler.send(str(subscription_data.subscribe_payload))
            return connection_key

        try:
            subscribe_payload = subscription_data.subscribe_payload
            self.subscriptions[connection_key] = (subscription_data, callback)

            handler = WebSocketApp(
                url=self.get_websocket_url(subscription_data.visibility),
                on_message=lambda ws, data: self._handle_message(connection_key, data),
                on_error=lambda ws, e: self._handle_error(connection_key, e),
                on_close=lambda ws, a, b: self._handle_close(connection_key)
            )

            thread = threading.Thread(
                target=handler.run_forever,
                daemon=False,
                name=f"WS-{self.provider_name}-{connection_key}"
            )
            thread.start()
            time.sleep(2)

            if subscription_data.visibility == SubscriptionVisibility.PRIVATE:
                if connection_key not in self.authenticated_connections and self.auth_handler:
                    handler.send(json.dumps(self.auth_handler.get_auth_request()))
                    self.authenticated_connections.add(connection_key)
                    time.sleep(1)

            handler.send(json.dumps(subscribe_payload))
            self.connections[connection_key] = handler
            logging.info(f"Subscribed to {connection_key} on {self.provider_name}")

            return connection_key
        except Exception as exc:
            logging.error(f"Subscription failed for {connection_key}: {exc}", exc_info=True)
            raise

    def unsubscribe(self, connection_key: str) -> None:
        try:
            if connection_key not in self.subscriptions:
                logging.warning(f"Subscription {connection_key} not found")
                return

            subscription_data, _ = self.subscriptions[connection_key]
            handler = self.connections.get(connection_key)
            if handler:
                handler.send(subscription_data.unsubscribe_payload)
                handler.close()
                del self.connections[connection_key]
            del self.subscriptions[connection_key]
            self.authenticated_connections.discard(connection_key)
            logging.info(f"Unsubscribed from {connection_key} on {self.provider_name}")
        except Exception as exc:
            logging.error(f"Unsubscription failed for {connection_key}: {exc}", exc_info=True)

    def _handle_message(self, connection_key: str, message: dict) -> None:
        try:
            data = json.loads(message)

            if self.auth_handler and self.auth_handler.is_auth_response(data):
                self.auth_handler.handle_auth_response(data)
                return

            if self.heartbeat_handler and self.heartbeat_handler.is_heartbeat(data):
                self._handle_heartbeat(connection_key, data)
                return

            if connection_key in self.subscriptions:
                _, callback = self.subscriptions[connection_key]
                try:
                    callback(connection_key, data)
                except Exception as exc:
                    logging.error(f"Error invoking callback for {connection_key}: {exc}", exc_info=True)
        except Exception as exc:
            logging.error(f"Error invoking callback for {connection_key}: {exc}", exc_info=True)

    def _handle_heartbeat(self, connection_key: str, message: dict) -> None:
        try:
            self.last_heartbeat[connection_key] = time.time()
            response = self.heartbeat_handler.get_heartbeat_response(message)
            if response:
                ws_connection = self.connections.get(connection_key)
                if ws_connection:
                    ws_connection.send(json.dumps(response))
                    logging.debug(f"Heartbeat response sent for {connection_key}")
            else:
                logging.debug(f"Heartbeat received for {connection_key}")

        except Exception as exc:
            logging.error(f"Error handling heartbeat for {connection_key}: {exc}", exc_info=True)

    def _handle_error(self, event_key: str, error: str) -> None:
        logging.error(f"WebSocket error for {event_key}: {error}")

    def _handle_close(self, event_key: str) -> None:
        logging.warning(f"WebSocket closed for {event_key}")
        self.subscriptions.pop(event_key, None)
