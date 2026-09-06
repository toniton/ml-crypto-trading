from __future__ import annotations

from src.metrics.services.metric_service import MetricService


class ExchangeMetricsCollector:
    def __init__(self, metric_service: MetricService):
        self._metric_service = metric_service

    def record_request(self, exchange: str, operation: str) -> None:
        labels = {"exchange": exchange, "operation": operation}
        self._metric_service.increment("exchange.requests", labels=labels)
        self._metric_service.flush()

    def record_duration(self, exchange: str, operation: str, duration_ms: float) -> None:
        labels = {"exchange": exchange, "operation": operation}
        self._metric_service.observe("exchange.request.duration", duration_ms, labels=labels)
        self._metric_service.flush()

    def record_error(self, exchange: str, operation: str, error_type: str) -> None:
        labels = {
            "exchange": exchange,
            "operation": operation,
            "error_type": error_type,
        }
        self._metric_service.increment("exchange.errors", labels=labels)
        self._metric_service.flush()

    def record_circuit_trip(self, exchange: str, operation: str) -> None:
        labels = {"exchange": exchange, "operation": operation}
        self._metric_service.increment("circuit_breaker.tripped", labels=labels)
        self._metric_service.flush()

    def record_websocket_message(self, exchange: str, message_type: str = "message") -> None:
        labels = {"exchange": exchange, "type": message_type}
        self._metric_service.increment("exchange.websocket.messages", labels=labels)
        self._metric_service.flush()

    def record_websocket_error(self, exchange: str, operation: str, error_type: str) -> None:
        labels = {
            "exchange": exchange,
            "operation": operation,
            "error_type": error_type,
        }
        self._metric_service.increment("exchange.websocket.errors", labels=labels)
        self._metric_service.increment("exchange.errors", labels=labels)
        self._metric_service.flush()

    def record_websocket_reconnect(self, exchange: str) -> None:
        labels = {"exchange": exchange}
        self._metric_service.increment("exchange.websocket.reconnects", labels=labels)
        self._metric_service.flush()
