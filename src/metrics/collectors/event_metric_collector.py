from __future__ import annotations

from typing import Optional

from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.events.message_event_bus import CallbackSubscription
from src.metrics.models.metric_type import AggregationType, MetricType
from src.metrics.services.metric_service import MetricService

DEFAULT_EVENT_METRICS = {
    "OrderSubmitted": "orders.submitted",
    "OrderSubmittedEvent": "orders.submitted",
    "OrderExecuted": "orders.executed",
    "OrderFilledEvent": "orders.executed",
    "OrderCancelled": "orders.cancelled",
    "OrderCancelledEvent": "orders.cancelled",
    "OrderRejected": "orders.rejected",
    "OrderRejectedEvent": "orders.rejected",
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

    @staticmethod
    def _extract_labels(event: Event) -> dict[str, str]:
        labels: dict[str, str] = {}
        order = getattr(event, "order", None)
        if order is None and hasattr(event, "payload") and isinstance(event.payload, dict):
            order = event.payload.get("order")

        if order is not None:
            provider = getattr(order, "provider_name", None)
            if provider is None and isinstance(order, dict):
                provider = order.get("provider_name")
            if provider:
                labels["provider"] = str(provider)

            symbol = getattr(order, "ticker_symbol", None)
            if symbol is None and isinstance(order, dict):
                symbol = order.get("ticker_symbol")
            if symbol:
                labels["symbol"] = str(symbol)

            action = getattr(order, "trade_action", None)
            if action is None and isinstance(order, dict):
                action = order.get("trade_action")
            if action:
                labels["action"] = action.value if hasattr(action, "value") else str(action)
        elif hasattr(event, "symbol") and getattr(event, "symbol"):
            labels["symbol"] = str(getattr(event, "symbol"))

        return labels

    def _record_latencies(self, event: Event, metric_name: str, labels: dict[str, str]) -> None:
        order = getattr(event, "order", None)
        if order is None and hasattr(event, "payload") and isinstance(event.payload, dict):
            order = event.payload.get("order")
        if order is None:
            return

        created_time = getattr(order, "created_time", None)
        if created_time is None and isinstance(order, dict):
            created_time = order.get("created_time")

        executed_time = getattr(order, "executed_time", None)
        if executed_time is None and isinstance(order, dict):
            executed_time = order.get("executed_time")

        if created_time is not None and executed_time is not None and executed_time >= created_time:
            latency_ms = (executed_time - created_time) * 1000.0
            if metric_name == "orders.executed":
                self._metric_service.observe("order.latency.execution", latency_ms, labels=labels)
            if metric_name in ("orders.executed", "orders.cancelled"):
                self._metric_service.observe("order.latency.terminal", latency_ms, labels=labels)
