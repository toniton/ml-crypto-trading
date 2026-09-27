from __future__ import annotations

from src.metrics.models.constants import MetricLabelKey, MetricName
from src.metrics.services.metric_service import MetricService


class ExchangeMetricsCollector:
    def __init__(self, metric_service: MetricService):
        self._metric_service = metric_service

    def record_request(self, exchange: str, operation: str) -> None:
        labels = {
            MetricLabelKey.EXCHANGE.value: exchange,
            MetricLabelKey.OPERATION.value: operation,
        }
        self._metric_service.increment(MetricName.EXCHANGE_REQUESTS.value, labels=labels)
        self._metric_service.flush()

    def record_duration(self, exchange: str, operation: str, duration_ms: float) -> None:
        labels = {
            MetricLabelKey.EXCHANGE.value: exchange,
            MetricLabelKey.OPERATION.value: operation,
        }
        self._metric_service.observe(MetricName.EXCHANGE_REQUEST_DURATION.value, duration_ms, labels=labels)
        self._metric_service.flush()

    def record_error(self, exchange: str, operation: str, error_type: str) -> None:
        labels = {
            MetricLabelKey.EXCHANGE.value: exchange,
            MetricLabelKey.OPERATION.value: operation,
            MetricLabelKey.ERROR_TYPE.value: error_type,
        }
        self._metric_service.increment(MetricName.EXCHANGE_ERRORS.value, labels=labels)
        self._metric_service.flush()

    def record_circuit_trip(self, exchange: str, operation: str) -> None:
        labels = {
            MetricLabelKey.EXCHANGE.value: exchange,
            MetricLabelKey.OPERATION.value: operation,
        }
        self._metric_service.increment(MetricName.CIRCUIT_BREAKER_TRIPPED.value, labels=labels)
        self._metric_service.flush()

    def record_websocket_message(self, exchange: str, message_type: str = "message") -> None:
        labels = {
            MetricLabelKey.EXCHANGE.value: exchange,
            MetricLabelKey.TYPE.value: message_type,
        }
        self._metric_service.increment(MetricName.EXCHANGE_WEBSOCKET_MESSAGES.value, labels=labels)
        self._metric_service.flush()

    def record_websocket_error(self, exchange: str, operation: str, error_type: str) -> None:
        labels = {
            MetricLabelKey.EXCHANGE.value: exchange,
            MetricLabelKey.OPERATION.value: operation,
            MetricLabelKey.ERROR_TYPE.value: error_type,
        }
        self._metric_service.increment(MetricName.EXCHANGE_WEBSOCKET_ERRORS.value, labels=labels)
        self._metric_service.increment(MetricName.EXCHANGE_ERRORS.value, labels=labels)
        self._metric_service.flush()

    def record_websocket_reconnect(self, exchange: str) -> None:
        labels = {MetricLabelKey.EXCHANGE.value: exchange}
        self._metric_service.increment(MetricName.EXCHANGE_WEBSOCKET_RECONNECTS.value, labels=labels)
        self._metric_service.flush()
