from __future__ import annotations

from typing import Optional

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.events.message_event_bus import CallbackSubscription
from src.events.runtime_events import (
    RuntimeErrorCapturedEvent,
    RuntimeIncidentCreatedEvent,
    RuntimeIncidentUpdatedEvent,
)
from src.events.trading_event import TradingEvent
from src.metrics.models.metric_type import AggregationType, MetricType
from src.metrics.services.metric_service import MetricService
from src.trading.events import (
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
)

DEFAULT_EVENT_METRICS = {
    OrderSubmittedEvent.__name__: "orders.submitted",
    OrderFilledEvent.__name__: "orders.executed",
    OrderCancelledEvent.__name__: "orders.cancelled",
    OrderRejectedEvent.__name__: "orders.rejected",
    RuntimeErrorCapturedEvent.__name__: "runtime.errors.total",
    RuntimeIncidentCreatedEvent.__name__: "runtime.incidents.total",
    RuntimeIncidentUpdatedEvent.__name__: "runtime.incident.occurrences",
}


class EventMetricCollector:
    """Subscribes to an :class:`EventBus` and increments counters and observes latencies per event."""

    def __init__(
            self,
            metric_service: MetricService,
            event_metric_map: Optional[dict[str, str]] = None,
    ):
        self._metric_service = metric_service
        self._event_metric_map = dict(event_metric_map or DEFAULT_EVENT_METRICS)
        self._subscription_ids: list[str] = []
        self._register_definitions()

    def _register_definitions(self) -> None:
        self._metric_service.register(
            "runtime.errors.total",
            metric_type=MetricType.COUNTER,
            unit="errors",
            description="Total captured runtime error count",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "runtime.incidents.total",
            metric_type=MetricType.COUNTER,
            unit="incidents",
            description="Total created runtime incidents",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "runtime.incident.occurrences",
            metric_type=MetricType.COUNTER,
            unit="occurrences",
            description="Total runtime incident occurrence increments",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "orders.submitted",
            metric_type=MetricType.COUNTER,
            unit="orders",
            description="Total submitted orders count",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "orders.executed",
            metric_type=MetricType.COUNTER,
            unit="orders",
            description="Total executed/filled orders count",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "orders.cancelled",
            metric_type=MetricType.COUNTER,
            unit="orders",
            description="Total cancelled orders count",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "orders.rejected",
            metric_type=MetricType.COUNTER,
            unit="orders",
            description="Total rejected orders count",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "order.latency.submit",
            metric_type=MetricType.HISTOGRAM,
            unit="ms",
            description="Signal to order submit latency in ms",
            aggregation=AggregationType.P95,
        )
        self._metric_service.register(
            "order.latency.execution",
            metric_type=MetricType.HISTOGRAM,
            unit="ms",
            description="Order submit to fill execution latency in ms",
            aggregation=AggregationType.P95,
        )
        self._metric_service.register(
            "order.latency.terminal",
            metric_type=MetricType.HISTOGRAM,
            unit="ms",
            description="Order submit to terminal state latency in ms",
            aggregation=AggregationType.P95,
        )

    def subscribe(self, event_bus: EventBus) -> list[str]:
        for event_type in self._event_metric_map:
            subscription_id = event_bus.subscribe(
                event_type, CallbackSubscription(self.on_event)
            )
            self._subscription_ids.append(subscription_id)
        return self._subscription_ids

    def on_event(self, event: Event) -> None:
        metric_name = self._event_metric_map.get(event.type)
        if not metric_name:
            return

        labels = self._extract_labels(event)
        self._metric_service.increment(metric_name, labels=labels)
        self._record_latencies(event, metric_name, labels)
        self._metric_service.flush()

    @classmethod
    def _extract_labels(cls, event: Event) -> dict[str, str]:
        payload_labels = cls._extract_payload_labels(event)
        if payload_labels is not None:
            return payload_labels

        labels = cls._extract_order_labels(event)
        if "symbol" not in labels and isinstance(event, TradingEvent) and event.asset:
            labels["symbol"] = str(event.asset)
        return labels

    @staticmethod
    def _extract_payload_labels(event: Event) -> Optional[dict[str, str]]:
        payload = None
        if isinstance(event, RuntimeErrorCapturedEvent):
            payload = event.event_payload
        elif isinstance(event, (RuntimeIncidentCreatedEvent, RuntimeIncidentUpdatedEvent)):
            payload = event.incident_payload

        if not isinstance(payload, dict):
            return None

        keys = ("exchange", "asset", "severity", "category", "component")
        return {key: str(payload[key]) for key in keys if payload.get(key)}

    @staticmethod
    def _extract_order(event: Event) -> Optional[Order | dict]:
        if isinstance(event, (OrderSubmittedEvent, OrderFilledEvent, OrderCancelledEvent, OrderRejectedEvent)):
            return event.order
        if isinstance(event.payload, dict):
            return event.payload.get("order")
        return None

    @classmethod
    def _extract_order_labels(cls, event: Event) -> dict[str, str]:
        labels: dict[str, str] = {}
        order = cls._extract_order(event)
        if order is None:
            return labels

        if isinstance(order, dict):
            provider = order.get("provider_name")
            symbol = order.get("ticker_symbol")
            action = order.get("trade_action")
        else:
            provider = order.provider_name
            symbol = order.ticker_symbol
            action = order.trade_action

        if provider:
            labels["provider"] = str(provider)
        if symbol:
            labels["symbol"] = str(symbol)
        if action:
            labels["action"] = action.value if isinstance(action, TradeAction) else str(action)

        return labels

    def _record_latencies(self, event: Event, metric_name: str, labels: dict[str, str]) -> None:
        order = self._extract_order(event)
        if order is None:
            return

        if isinstance(order, dict):
            created_time = order.get("created_time")
            executed_time = order.get("executed_time")
        else:
            created_time = order.created_time
            executed_time = order.executed_time

        if created_time is not None and executed_time is not None and executed_time >= created_time:
            latency_ms = (executed_time - created_time) * 1000.0
            if metric_name == "orders.executed":
                self._metric_service.observe("order.latency.execution", latency_ms, labels=labels)
            if metric_name in ("orders.executed", "orders.cancelled"):
                self._metric_service.observe("order.latency.terminal", latency_ms, labels=labels)
