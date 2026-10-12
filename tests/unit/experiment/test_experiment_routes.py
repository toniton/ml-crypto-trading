from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.routes.experiment_routes import create_experiment_router


class TestExperimentRoutes:  # pylint: disable=attribute-defined-outside-init
    def setup_method(self):
        self.app = FastAPI()
        self.mock_service = MagicMock()
        self.app.state.experiment_service = self.mock_service
        self.app.include_router(create_experiment_router())
        self.client = TestClient(self.app)

    def test_create_experiment_route(self):
        self.mock_service.create_experiment.return_value = {
            "experiment_id": "exp_abc123",
            "name": "Test Run",
            "ticker_symbol": "BTC_USD",
            "status": "DRAFT",
        }

        response = self.client.post(
            "/api/v1/experiments",
            json={"name": "Test Run", "ticker_symbol": "BTC_USD"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["experiment_id"] == "exp_abc123"
        assert data["status"] == "DRAFT"

    def test_list_experiments_route(self):
        self.mock_service.list_experiments.return_value = [
            {"experiment_id": "exp_1", "name": "Run 1"},
            {"experiment_id": "exp_2", "name": "Run 2"},
        ]

        response = self.client.get("/api/v1/experiments?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["experiment_id"] == "exp_1"

    def test_get_experiment_route_found_and_not_found(self):
        self.mock_service.get_experiment.side_effect = lambda eid: (
            {"experiment_id": eid, "name": "Run Found"} if eid == "exp_exist" else None
        )

        res_ok = self.client.get("/api/v1/experiments/exp_exist")
        assert res_ok.status_code == 200
        assert res_ok.json()["name"] == "Run Found"

        res_404 = self.client.get("/api/v1/experiments/exp_missing")
        assert res_404.status_code == 404

    def test_delete_experiment_route(self):
        self.mock_service.delete_experiment.side_effect = lambda eid: eid == "exp_to_delete"

        res_ok = self.client.delete("/api/v1/experiments/exp_to_delete")
        assert res_ok.status_code == 200
        assert res_ok.json()["deleted"] is True

        res_404 = self.client.delete("/api/v1/experiments/exp_missing")
        assert res_404.status_code == 404

    def test_start_experiment_route(self):
        self.mock_service.start_experiment.return_value = {
            "experiment_id": "exp_start_1",
            "status": "RUNNING",
        }
        res = self.client.post("/api/v1/experiments/exp_start_1/start")
        assert res.status_code == 200
        assert res.json()["status"] == "RUNNING"

    def test_cancel_experiment_route(self):
        self.mock_service.cancel_experiment.side_effect = lambda eid: eid == "exp_to_cancel"
        res_ok = self.client.post("/api/v1/experiments/exp_to_cancel/cancel")
        assert res_ok.status_code == 200
        assert res_ok.json()["cancelled"] is True

        res_404 = self.client.post("/api/v1/experiments/exp_missing/cancel")
        assert res_404.status_code == 404

    def test_retry_candidate_route(self):
        self.mock_service.retry_candidate.return_value = {
            "experiment_id": "exp_1",
            "status": "RUNNING",
        }
        res = self.client.post("/api/v1/experiments/exp_1/candidates/cand_1/retry")
        assert res.status_code == 200
        assert res.json()["status"] == "RUNNING"
