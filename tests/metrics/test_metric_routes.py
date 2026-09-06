from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.metrics.api.metric_routes import create_metric_router
from src.metrics.services.metric_service import MetricService


class TestMetricRoutes:
    def test_get_metric_series(self, db_manager):
        service = MetricService(db_manager)
        service.increment("http.requests")
        service.increment("http.requests")
        service.flush()

        app = FastAPI()
        app.include_router(create_metric_router(service))
        client = TestClient(app)

        response = client.get("/metrics/http.requests")

        assert response.status_code == 200
        data = response.json()
        assert data["metric"] == "http.requests"
        assert data["interval"] == 60
        assert len(data["series"]) == 1

    def test_list_metrics(self, db_manager):
        service = MetricService(db_manager)
        service.increment("http.requests")
        service.increment("http.errors")
        service.flush()

        app = FastAPI()
        app.include_router(create_metric_router(service))
        client = TestClient(app)

        response = client.get("/metrics")

        assert response.status_code == 200
        assert response.json()["metrics"] == ["http.errors", "http.requests"]

    def test_unknown_metric_returns_404(self, db_manager):
        service = MetricService(db_manager)

        app = FastAPI()
        app.include_router(create_metric_router(service))
        client = TestClient(app)

        response = client.get("/metrics/does.not.exist")

        assert response.status_code == 404

    def test_exchange_health_metrics_queries(self, db_manager):
        service = MetricService(db_manager)
        service.increment("exchange.requests", labels={"exchange": "BINANCE", "operation": "get_candles"})
        service.increment("exchange.errors", labels={"exchange": "BINANCE", "operation": "get_candles"})
        service.increment("circuit_breaker.tripped", labels={"exchange": "BINANCE", "operation": "get_candles"})
        service.flush()

        app = FastAPI()
        app.include_router(create_metric_router(service))
        client = TestClient(app)

        res_req = client.get("/metrics/exchange.requests?interval=60")
        assert res_req.status_code == 200
        assert res_req.json()["metric"] == "exchange.requests"
        assert len(res_req.json()["series"]) == 1

        res_err = client.get("/metrics/exchange.errors?interval=60")
        assert res_err.status_code == 200
        assert res_err.json()["metric"] == "exchange.errors"

        res_trip = client.get("/metrics/circuit_breaker.tripped?interval=60")
        assert res_trip.status_code == 200
        assert res_trip.json()["metric"] == "circuit_breaker.tripped"

