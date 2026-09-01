from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware

from src.metrics.services.metric_service import MetricService


class RequestMetricsCollector:
    def __init__(self, metric_service: MetricService):
        self._metric_service = metric_service

    @staticmethod
    def _status_class(status_code: int) -> str:
        return f"{status_code // 100}xx"

    def record_request(
            self,
            method: str,
            route: str,
            status_code: int,
            duration_ms: float,
    ) -> None:
        labels = {
            "method": method,
            "route": route,
            "status_class": RequestMetricsCollector._status_class(status_code),
        }
        self._metric_service.increment("http.requests", labels=labels)
        self._metric_service.observe("http.request.duration", duration_ms, labels=labels)
        if status_code >= 400:
            self._metric_service.increment("http.errors", labels=labels)


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, collector: RequestMetricsCollector):
        super().__init__(app)
        self._collector = collector

    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        try:
            self._collector.record_request(
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
        except Exception:  # pylint: disable=broad-except
            # Metrics must never affect the request/response path.
            pass
        return response
