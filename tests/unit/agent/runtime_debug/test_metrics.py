from unittest.mock import MagicMock

from src.events.runtime_events import (
    RuntimeErrorCapturedEvent,
    RuntimeIncidentCreatedEvent,
)
from src.metrics.collectors.event_metric_collector import EventMetricCollector
from src.metrics.services.metric_service import MetricService


def test_event_metric_collector_handles_runtime_events():
    metric_service = MagicMock(spec=MetricService)
    collector = EventMetricCollector(metric_service=metric_service)

    error_ev = RuntimeErrorCapturedEvent(
        event_payload={
            "exchange": "CRYPTO_DOT_COM",
            "asset": "BTC_USD",
            "severity": "CRITICAL",
            "category": "EXCHANGE_VALIDATION",
            "component": "trading.orders.order_manager",
        }
    )
    collector.on_event(error_ev)

    metric_service.increment.assert_called_with(
        "runtime.errors.total",
        labels={
            "exchange": "CRYPTO_DOT_COM",
            "asset": "BTC_USD",
            "severity": "CRITICAL",
            "category": "EXCHANGE_VALIDATION",
            "component": "trading.orders.order_manager",
        },
    )

    incident_ev = RuntimeIncidentCreatedEvent(
        incident_payload={
            "exchange": "CRYPTO_DOT_COM",
            "asset": "BTC_USD",
            "severity": "CRITICAL",
            "category": "EXCHANGE_VALIDATION",
        }
    )
    collector.on_event(incident_ev)

    metric_service.increment.assert_called_with(
        "runtime.incidents.total",
        labels={
            "exchange": "CRYPTO_DOT_COM",
            "asset": "BTC_USD",
            "severity": "CRITICAL",
            "category": "EXCHANGE_VALIDATION",
        },
    )
