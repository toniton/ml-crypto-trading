from __future__ import annotations

from typing import Optional

from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.events.message_event_bus import CallbackSubscription
from src.metrics.services.metric_service import MetricService

DEFAULT_EVENT_METRICS = {
    "OrderSubmitted": "orders.submitted",
    "OrderSubmittedEvent": "orders.submitted",
    "OrderExecuted": "orders.executed",
    "OrderFilledEvent": "orders.executed",
    "OrderCancelled": "orders.cancelled",
    "OrderCancelledEvent": "orders.cancelled",
}


class EventMetricCollector:
    """Subscribes to an :class:`EventBus` and increments counters per event.

    The mapping between event type names and metric names is configurable, so
    any subsystem can feed metrics through the bus without depending on
    :class:`MetricService` directly.
    """

    def __init__(
            self,
            metric_service: MetricService,
            event_metric_map: Optional[dict[str, str]] = None,
    ):
        self._metric_service = metric_service
        self._event_metric_map = dict(event_metric_map or DEFAULT_EVENT_METRICS)
        self._subscription_ids: list[str] = []

    def subscribe(self, event_bus: EventBus) -> list[str]:
        for event_type in self._event_metric_map:
            subscription_id = event_bus.subscribe(
                event_type, CallbackSubscription(self.on_event)
            )
            self._subscription_ids.append(subscription_id)
        return self._subscription_ids

    def on_event(self, event: Event) -> None:
        metric_name = self._event_metric_map.get(event.type)
        if metric_name:
            self._metric_service.increment(metric_name)
