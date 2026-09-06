from __future__ import annotations

import threading
from typing import Callable, Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.timeframe import Timeframe
from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.subscription_data import SubscriptionVisibility
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.exchange.registries.websocket_registry import WebSocketRegistry
from src.metrics.collectors.exchange_metrics_collector import ExchangeMetricsCollector


class WebSocketManager(WebSocketRegistry, ApplicationLoggingMixin):
    def __init__(self, metrics_collector: Optional[ExchangeMetricsCollector] = None):
        super().__init__()
        self._lock = threading.Lock()
        self._subscriptions: dict[str, dict[str, tuple[ExchangeWebSocketBuilder, Callable]]] = {}
        self._on_reconnect: Callable | None = None
        self._metrics_collector = metrics_collector

    def set_reconnect_callback(self, callback: Callable) -> None:
        def on_reconnect_wrapper(*args, **kwargs):
            if self._metrics_collector:
                self._metrics_collector.record_websocket_reconnect("all")
            return callback(*args, **kwargs)

        self._on_reconnect = on_reconnect_wrapper

    def register_service(self, service: ExchangeWebSocketService):
        super().register_service(service)
        provider_name = service.get_provider_name()
        if provider_name not in self._subscriptions:
            self._subscriptions[provider_name] = {}

    def connect(self):
        for service_name in self.get_registered_services():
            service = self.get_service(service_name)
            service.set_reconnect_callback(self._on_reconnect)
            service.connect(self._handle_incoming_message)

    def _handle_incoming_message(self, exchange: str, visibility: SubscriptionVisibility, data: dict):
        if self._metrics_collector:
            self._metrics_collector.record_websocket_message(exchange, visibility.value)

        callbacks_to_call = []
        with self._lock:
            if exchange not in self._subscriptions:
                return

            for key, (builder, callback) in self._subscriptions[exchange].items():
                sub_data = builder.get_subscription_data()
                if sub_data.visibility == visibility and sub_data.matches(data):
                    callbacks_to_call.append((key, builder, callback))

        for key, builder, callback in callbacks_to_call:
            try:
                sub_data = builder.get_subscription_data()
                parsed_data = sub_data.parse(data)
                if parsed_data:
                    callback(parsed_data)
            except Exception as e:
                if self._metrics_collector:
                    self._metrics_collector.record_websocket_error(exchange, key, type(e).__name__)
                self.app_logger.error(
                    f"Error parsing/executing callback for {key} on {exchange}: {e}",
                    exc_info=True
                )

    def subscribe_market_data(self, exchange: str, ticker_symbol: str, callback: Callable[[MarketData], None]):
        key = f"MARKET_{ticker_symbol}"
        service = self.get_service(exchange)
        builder = service.builder().market_data(ticker_symbol)
        self._subscribe(key, service, builder, callback)

    def subscribe_candles(
            self, exchange: str, ticker_symbol: str,
            timeframe: Timeframe, callback: Callable[[list[Candle]], None]
    ):
        key = f"CANDLES_{ticker_symbol}_{timeframe.value}"
        service = self.get_service(exchange)
        builder = service.builder().candles(ticker_symbol, timeframe)
        self._subscribe(key, service, builder, callback)

    def subscribe_account_balance(self, exchange: str, callback: Callable[[AccountBalance], None]):
        key = "BALANCE"
        service = self.get_service(exchange)
        builder = service.builder().account_balance()
        self._subscribe(key, service, builder, callback)

    def subscribe_order_update(self, exchange: str, instrument_name: str, callback: Callable[[list[Order]], None]):
        key = f"ORDER_{instrument_name}"
        service = self.get_service(exchange)
        builder = service.builder().order_update(instrument_name)
        self._subscribe(key, service, builder, callback)

    def _subscribe(
            self, key: str, service: ExchangeWebSocketService,
            builder: ExchangeWebSocketBuilder, callback: Callable
    ):
        service_name = service.get_provider_name()
        with self._lock:
            self._subscriptions[service_name][key] = (builder, callback)
            service.subscribe(builder)

    def unsubscribe_market_data(self, exchange: str, ticker_symbol: str):
        key = f"MARKET_{ticker_symbol}"
        self._unsubscribe(exchange, key)

    def unsubscribe_candles(self, exchange: str, ticker_symbol: str, timeframe: Timeframe):
        key = f"CANDLES_{ticker_symbol}_{timeframe.value}"
        self._unsubscribe(exchange, key)

    def unsubscribe_account_balance(self, exchange: str):
        key = "BALANCE"
        self._unsubscribe(exchange, key)

    def unsubscribe_order_update(self, exchange: str, instrument_name: str):
        key = f"ORDER_{instrument_name}"
        self._unsubscribe(exchange, key)

    def _unsubscribe(self, exchange: str, key: str):
        service = self.get_service(exchange)
        with self._lock:
            if exchange not in self._subscriptions or key not in self._subscriptions[exchange]:
                return

            builder, _ = self._subscriptions[exchange][key]
            service.unsubscribe(builder)
            del self._subscriptions[exchange][key]

        self.app_logger.info(f"Unsubscribed from {key} on {exchange}")
