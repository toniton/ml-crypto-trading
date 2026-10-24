from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.routes.walk_forward_routes import create_walk_forward_router


class TestWalkForwardRoutes:
    def setup_method(self):
        self.app = FastAPI()
        self.mock_service = MagicMock()
        self.app.state.walk_forward_service = self.mock_service
        self.app.include_router(create_walk_forward_router())
        self.client = TestClient(self.app)

    def test_start_walk_forward_run_route(self):
        self.mock_service.start_run.return_value = {
            "run_id": "wf_test_123",
            "status": "QUEUED",
            "ticker_symbol": "BTC_USD",
        }

        response = self.client.post(
            "/api/v1/walk-forward",
            json={"ticker_symbol": "BTC_USD"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["run_id"] == "wf_test_123"
        assert data["status"] == "QUEUED"

    def test_list_walk_forward_runs_route(self):
        self.mock_service.list_runs.return_value = [
            {"run_id": "wf_1", "status": "COMPLETED"},
            {"run_id": "wf_2", "status": "RUNNING"},
        ]

        response = self.client.get("/api/v1/walk-forward?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["run_id"] == "wf_1"

    def test_get_walk_forward_run_route(self):
        self.mock_service.get_run.side_effect = lambda rid: (
            {"run_id": rid, "status": "COMPLETED"} if rid == "wf_found" else None
        )

        res_ok = self.client.get("/api/v1/walk-forward/wf_found")
        assert res_ok.status_code == 200
        assert res_ok.json()["run_id"] == "wf_found"

        res_404 = self.client.get("/api/v1/walk-forward/wf_missing")
        assert res_404.status_code == 404

    def test_cancel_walk_forward_run_success(self):
        self.mock_service.cancel_run.return_value = True

        response = self.client.post("/api/v1/walk-forward/wf_running/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "wf_running"
        assert data["cancelled"] is True
        self.mock_service.cancel_run.assert_called_once_with("wf_running")

    def test_cancel_walk_forward_run_not_found(self):
        self.mock_service.cancel_run.return_value = False

        response = self.client.post("/api/v1/walk-forward/wf_missing/cancel")
        assert response.status_code == 404
