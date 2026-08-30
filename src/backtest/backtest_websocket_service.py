from __future__ import annotations

from typing import Any, Callable, Optional

from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.backtest_websocket_builder import BacktestWebSocketBuilder
from src.backtest.events.domain_events import (
    BalanceUpdateEvent,
    CandlesEvent,
    BacktestEvent,
    MarketDataEvent,
    OrderFillEvent,
)
from src.core.interfaces.auth_handler import AuthHandler
from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.heartbeat_handler import HeartbeatHandler
from src.core.interfaces.subscription_data import (
    SubscriptionData,
    SubscriptionVisibility,
)
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum


class BacktestWebSocketService(ExchangeWebSocketService):
    def __init__(self, event_bus: BacktestEventBus):
        self.bus = event_bus
        self._callback: Optional[Callable] = None
        self._subscriptions: dict[str, tuple[SubscriptionData, type[BacktestEvent] | None]] = {}
        self._bus_subscriptions: dict[type[BacktestEvent], int] = {}
        self._event_handlers: dict[type[BacktestEvent], Callable[[Any], None]] = {
            MarketDataEvent: self._handle_market_data_event,
            CandlesEvent: self._handle_candles_event,
            OrderFillEvent: self._handle_order_fill_event,
            BalanceUpdateEvent: self._handle_balance_update_event,
        }

    def get_provider_name(self) -> str:
        return ExchangeProvidersEnum.BACKTEST.value

    def get_websocket_url(self, visibility: SubscriptionVisibility) -> str:
        return "backtest://event-bus"

    def get_auth_request(self) -> dict:
        return {}

    def get_auth_handler(self) -> Optional[AuthHandler]:
        return None

    def get_heartbeat_handler(self) -> Optional[HeartbeatHandler]:
        return None

    def builder(self) -> BacktestWebSocketBuilder:
        return BacktestWebSocketBuilder(self.bus)

    def connect(self, callback: Callable):
        self._callback = callback

    def subscribe(self, builder: ExchangeWebSocketBuilder):
        sub_data = builder.get_subscription_data()
        event_class = getattr(builder, "event_class", None) if isinstance(builder, BacktestWebSocketBuilder) else None

        self._subscriptions[builder.key] = (sub_data, event_class)

        if event_class and event_class not in self._bus_subscriptions:
            handler = self._event_handlers.get(event_class)
            if handler:
                sub_id = self.bus.subscribe_callback(event_class, handler)
                self._bus_subscriptions[event_class] = sub_id

    def unsubscribe(self, builder: ExchangeWebSocketBuilder):
        if builder.key not in self._subscriptions:
            return

        _, event_class = self._subscriptions.pop(builder.key)

        if event_class and event_class in self._bus_subscriptions:
            # Check if any other active subscription still needs this event class
            still_needed = any(
                ec == event_class
                for _, ec in self._subscriptions.values()
            )
            if not still_needed:
                sub_id = self._bus_subscriptions.pop(event_class)
                self.bus.unsubscribe(sub_id)

    def _handle_market_data_event(self, event: MarketDataEvent):
        self._dispatch(
            exchange=self.get_provider_name(),
            visibility=SubscriptionVisibility.PUBLIC,
            data={"type": "market_data", "ticker_symbol": event.ticker_symbol, "data": event.market_data}
        )

    def _handle_candles_event(self, event: CandlesEvent):
        self._dispatch(
            exchange=self.get_provider_name(),
            visibility=SubscriptionVisibility.PUBLIC,
            data={"type": "candles", "ticker_symbol": event.ticker_symbol, "data": event.candles}
        )

    def _handle_order_fill_event(self, event: OrderFillEvent):
        # Even if the order has a provider_name, we route through BACKTEST in simulation
        self._dispatch(
            exchange=self.get_provider_name(),
            visibility=SubscriptionVisibility.PRIVATE,
            data={"type": "order_update", "instrument_name": event.order.ticker_symbol, "data": [event.order]}
        )

    def _handle_balance_update_event(self, event: BalanceUpdateEvent):
        # Simplified: dispatch only for the BACKTEST exchange
        self._dispatch(
            exchange=self.get_provider_name(),
            visibility=SubscriptionVisibility.PRIVATE,
            data={"type": "balance", "data": event.balances}
        )

    def _dispatch(self, exchange: str, visibility: SubscriptionVisibility, data: dict):
        if self._callback:
            self._callback(exchange, visibility, data)
