from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.metrics.collectors.request_metrics_collector import (
    RequestMetricsCollector,
    RequestMetricsMiddleware,
)
from src.metrics.models.metric_query import MetricQuery
from src.metrics.services.metric_service import MetricService


class TestRequestMetricsCollector:
    def test_records_requests_errors_and_duration(self, db_manager):
        service = MetricService(db_manager)
        collector = RequestMetricsCollector(service)

        collector.record_request("GET", "/orders", 200, 12.5)
        collector.record_request("POST", "/orders", 500, 20.0)

        requests = service.query(MetricQuery(metric_names=("http.requests",), interval_seconds=60))[0]
        errors = service.query(MetricQuery(metric_names=("http.errors",), interval_seconds=60))[0]
        durations = service.query(
            MetricQuery(metric_names=("http.request.duration",), interval_seconds=60)
        )[0]

        assert [point.value for point in requests.points] == [2.0]
        assert [point.value for point in errors.points] == [1.0]
        assert [point.value for point in durations.points] == [16.25]


class TestRequestMetricsMiddleware:
    def test_middleware_records_requests(self, db_manager):
        service = MetricService(db_manager)
        collector = RequestMetricsCollector(service)

        app = FastAPI()
        app.add_middleware(RequestMetricsMiddleware, collector=collector)

        @app.get("/hello")
        def hello():
            return {"ok": True}

        client = TestClient(app)
        client.get("/hello")
        client.get("/hello")

        series = service.query(MetricQuery(metric_names=("http.requests",), interval_seconds=60))[0]
        assert [point.value for point in series.points] == [2.0]
