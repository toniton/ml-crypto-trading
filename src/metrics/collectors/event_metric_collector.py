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
from src.metrics.models.constants import MetricLabelKey, MetricName, MetricUnit
from src.metrics.models.metric_type import AggregationType, MetricType
from src.metrics.services.metric_service import MetricService
from src.trading.events import (
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
)

DEFAULT_EVENT_METRICS: dict[str, str] = {
    OrderSubmittedEvent.__name__: MetricName.ORDERS_SUBMITTED_TOTAL.value,
    OrderFilledEvent.__name__: MetricName.ORDERS_FILLED_TOTAL.value,
    OrderCancelledEvent.__name__: MetricName.ORDERS_CANCELLED_TOTAL.value,
    OrderRejectedEvent.__name__: MetricName.ORDERS_REJECTED_TOTAL.value,
    RuntimeErrorCapturedEvent.__name__: MetricName.RUNTIME_ERRORS_TOTAL.value,
    RuntimeIncidentCreatedEvent.__name__: MetricName.RUNTIME_INCIDENTS_TOTAL.value,
    RuntimeIncidentUpdatedEvent.__name__: MetricName.RUNTIME_INCIDENT_OCCURRENCES.value,
}

_INCIDENT_PAYLOAD_LABEL_KEYS: tuple[str, ...] = (
    MetricLabelKey.EXCHANGE.value,
    "asset",
    MetricLabelKey.SEVERITY.value,
    MetricLabelKey.CATEGORY.value,
    MetricLabelKey.COMPONENT.value,
)


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
            MetricName.RUNTIME_ERRORS_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.ERRORS.value,
            description="Total captured runtime error count",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.RUNTIME_INCIDENTS_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.INCIDENTS.value,
            description="Total created runtime incidents",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.RUNTIME_INCIDENT_OCCURRENCES.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.OCCURRENCES.value,
            description="Total runtime incident occurrence increments",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.ORDERS_SUBMITTED_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.ORDERS.value,
            description="Total submitted orders count",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.ORDERS_FILLED_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.ORDERS.value,
            description="Total executed/filled orders count",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.ORDERS_CANCELLED_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.ORDERS.value,
            description="Total cancelled orders count",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.ORDERS_REJECTED_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.ORDERS.value,
            description="Total rejected orders count",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.ORDER_LATENCY_SUBMIT.value,
            metric_type=MetricType.HISTOGRAM,
            unit=MetricUnit.MILLISECONDS.value,
            description="Signal to order submit latency in ms",
            aggregation=AggregationType.P95,
        )
        self._metric_service.register(
            MetricName.ORDER_LATENCY_EXECUTION.value,
            metric_type=MetricType.HISTOGRAM,
            unit=MetricUnit.MILLISECONDS.value,
            description="Order submit to fill execution latency in ms",
            aggregation=AggregationType.P95,
        )
        self._metric_service.register(
            MetricName.ORDER_LATENCY_TERMINAL.value,
            metric_type=MetricType.HISTOGRAM,
            unit=MetricUnit.MILLISECONDS.value,
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
        if MetricLabelKey.SYMBOL.value not in labels and isinstance(event, TradingEvent) and event.asset:
            labels[MetricLabelKey.SYMBOL.value] = str(event.asset)
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

        return {key: str(payload[key]) for key in _INCIDENT_PAYLOAD_LABEL_KEYS if payload.get(key)}

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
            labels[MetricLabelKey.PROVIDER.value] = str(provider)
        if symbol:
            labels[MetricLabelKey.SYMBOL.value] = str(symbol)
        if action:
            labels[MetricLabelKey.ACTION.value] = (
                action.value if isinstance(action, TradeAction) else str(action)
            )

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
            if metric_name in (MetricName.ORDERS_FILLED_TOTAL.value, "orders.executed"):
                self._metric_service.observe(MetricName.ORDER_LATENCY_EXECUTION.value, latency_ms, labels=labels)
            if metric_name in (
                    MetricName.ORDERS_FILLED_TOTAL.value,
                    "orders.executed",
                    MetricName.ORDERS_CANCELLED_TOTAL.value,
                    "orders.cancelled",
            ):
                self._metric_service.observe(MetricName.ORDER_LATENCY_TERMINAL.value, latency_ms, labels=labels)
