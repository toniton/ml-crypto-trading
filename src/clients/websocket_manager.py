import json
import threading
import time
from typing import Callable

from websocket import WebSocketApp

from api.interfaces.timeframe import Timeframe
from src.core.interfaces.exchange_websocket_client import ExchangeWebSocketClient
from src.core.interfaces.subscription_data import SubscriptionVisibility, SubscriptionData
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin

from src.core.registries.websocket_registry import WebSocketRegistry


class WebSocketManager(ApplicationLoggingMixin, WebSocketRegistry):

    def __init__(self):
        super().__init__()
        self._connections: dict[str, dict[SubscriptionVisibility, WebSocketApp]] = {}
        self._subscriptions: dict[str, dict[str, tuple[SubscriptionData, Callable]]] = {}
        self._authenticated_connections: set[str] = set()
        self._last_heartbeat: dict[str, float] = {}

    def register_websocket(self, websocket_client: ExchangeWebSocketClient):
        super().register_websocket(websocket_client)
        provider_name = websocket_client.get_provider_name()
        if provider_name not in self._connections:
            self._connections[provider_name] = {}
            self._subscriptions[provider_name] = {}

    def connect(self, exchange: str):
        client = self.get_websocket(exchange)
        self._ensure_connection(client, SubscriptionVisibility.PUBLIC)
        self._ensure_connection(client, SubscriptionVisibility.PRIVATE)

    def _ensure_connection(self, client: ExchangeWebSocketClient, visibility: SubscriptionVisibility):
        exchange = client.get_provider_name()
        if visibility in self._connections[exchange]:
            return

        url = client.get_websocket_url(visibility)
        conn_id = f"{exchange}-{visibility.value}"

        if url.startswith("backtest://"):
            self._connections[exchange][visibility] = None  # Marker for backtest connection
            self.app_logger.info(f"Initialized mock WebSocket connection for {conn_id}")
            return

        handler = WebSocketApp(
            url=url,
            on_message=lambda ws, data: self._handle_message(exchange, visibility, data),
            on_error=lambda ws, e: self.app_logger.error(f"WebSocket error for {conn_id}: {e}"),
            on_close=lambda ws, code, msg: self._handle_close(exchange, visibility, code, msg)
        )

        self._connections[exchange][visibility] = handler

        thread = threading.Thread(
            target=handler.run_forever,
            daemon=True,
            name=f"WS-{conn_id}"
        )
        thread.start()
        self.app_logger.info(f"Started WebSocket connection for {conn_id}")

        # Wait a bit for connection to establish
        time.sleep(1)

        if visibility == SubscriptionVisibility.PRIVATE:
            auth_handler = client.get_auth_handler()
            if auth_handler:
                handler.send(json.dumps(auth_handler.get_auth_request()))
                self._authenticated_connections.add(conn_id)
                self.app_logger.info(f"Sent auth request for {conn_id}")

    def subscribe_market_data(self, exchange: str, ticker_symbol: str, callback: Callable):
        client = self.get_websocket(exchange).market_data(ticker_symbol)
        sub_data = client.get_subscription_data()
        key = f"MARKET_{ticker_symbol}"
        self._subscribe(exchange, key, sub_data, callback)

    def subscribe_candles(self, exchange: str, ticker_symbol: str, timeframe: Timeframe, callback: Callable):
        client = self.get_websocket(exchange).candles(ticker_symbol, timeframe)
        sub_data = client.get_subscription_data()
        key = f"CANDLES_{ticker_symbol}_{timeframe.value}"
        self._subscribe(exchange, key, sub_data, callback)

    def subscribe_account_balance(self, exchange: str, callback: Callable):
        client = self.get_websocket(exchange).account_balance()
        sub_data = client.get_subscription_data()
        key = "BALANCE"
        self._subscribe(exchange, key, sub_data, callback)

    def subscribe_order_update(self, exchange: str, instrument_name: str, callback: Callable):
        client = self.get_websocket(exchange).order_update(instrument_name)
        sub_data = client.get_subscription_data()
        key = f"ORDER_{instrument_name}"
        self._subscribe(exchange, key, sub_data, callback)

    def _subscribe(self, exchange: str, key: str, sub_data: SubscriptionData, callback: Callable):
        self._ensure_connection(self.get_websocket(exchange), sub_data.visibility)
        handler = self._connections[exchange][sub_data.visibility]

        self._subscriptions[exchange][key] = (sub_data, callback)
        if handler:
            handler.send(json.dumps(sub_data.payload))
            self.app_logger.info(f"Subscribed to {key} on {exchange}")
        else:
            self.app_logger.info(f"Subscribed (backtest) to {key} on {exchange}")

    def unsubscribe_market_data(self, exchange: str, ticker_symbol: str):
        self._unsubscribe(exchange, f"MARKET_{ticker_symbol}")

    def unsubscribe_candles(self, exchange: str, ticker_symbol: str, timeframe: Timeframe):
        self._unsubscribe(exchange, f"CANDLES_{ticker_symbol}_{timeframe.value}")

    def unsubscribe_account_balance(self, exchange: str):
        self._unsubscribe(exchange, "BALANCE")

    def unsubscribe_order_update(self, exchange: str, instrument_name: str):
        self._unsubscribe(exchange, f"ORDER_{instrument_name}")

    def _unsubscribe(self, exchange: str, key: str):
        if exchange in self._subscriptions and key in self._subscriptions[exchange]:
            sub_data, _ = self._subscriptions[exchange][key]
            handler = self._connections[exchange].get(sub_data.visibility)
            if handler:
                client = self.get_websocket(exchange)
                unsub_payload = client.get_unsubscribe_payload(sub_data.payload)
                handler.send(json.dumps(unsub_payload))
            del self._subscriptions[exchange][key]
            self.app_logger.info(f"Unsubscribed from {key} on {exchange}")

    def _handle_message(self, exchange: str, visibility: SubscriptionVisibility, message: str):
        try:
            data = json.loads(message)
            self.inject_message(exchange, visibility, data)
        except Exception as e:
            self.app_logger.error(f"Error handling message from {exchange}: {e}", exc_info=True)

    def inject_message(self, exchange: str, visibility: SubscriptionVisibility, data: dict):
        client = self.get_websocket(exchange)

        # Auth handling
        auth_handler = client.get_auth_handler()
        if auth_handler and auth_handler.is_auth_response(data):
            auth_handler.handle_auth_response(data)
            return

        # Heartbeat handling
        heartbeat_handler = client.get_heartbeat_handler()
        if heartbeat_handler and heartbeat_handler.is_heartbeat(data):
            conn_id = f"{exchange}-{visibility.value}"
            self._last_heartbeat[conn_id] = time.time()
            response = heartbeat_handler.get_heartbeat_response(data)
            if response and self._connections[exchange][visibility]:
                self._connections[exchange][visibility].send(json.dumps(response))
            return

        # Subscription callbacks
        for _key, (sub_data, callback) in self._subscriptions[exchange].items():
            if sub_data.visibility == visibility and sub_data.matches(data):
                try:
                    parsed_data = sub_data.parse(data)
                    if parsed_data:
                        callback(parsed_data)
                except Exception:
                    continue

    def _handle_close(self, exchange: str, visibility: SubscriptionVisibility, code: int, msg: str):
        conn_id = f"{exchange}-{visibility.value}"
        self.app_logger.info(f"WebSocket closed for {conn_id}. Code: {code}, Msg: {msg}")

        if conn_id in self._authenticated_connections:
            self._authenticated_connections.remove(conn_id)

        if exchange in self._connections:
            self._connections[exchange].pop(visibility, None)

        # Immediate reconnect logic could go here, or handled by a supervisor.
        if code != 1000:
            self.app_logger.warning(f"Abnormal closure for {conn_id}, attempting to reconnect...")
            # Re-establishing connection will happen on next subscribe, or we can trigger it here.
            # For simplicity, we just clear it so next use reconnects.
