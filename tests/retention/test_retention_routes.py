from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.configuration.retention_config import RetentionConfig
from src.retention.manager import RetentionManager
from src.server.routes.retention_routes import RetentionRouterFactory


class TestRetentionRoutes:
    def _build_client(self, db_manager) -> TestClient:
        manager = RetentionManager(db_manager, config=RetentionConfig())
        app = FastAPI()
        app.include_router(RetentionRouterFactory.create_router(manager))
        return TestClient(app)

    def test_status_endpoint(self, db_manager):
        client = self._build_client(db_manager)
        response = client.get("/api/v1/retention/status")
        assert response.status_code == 200
        body = response.json()
        assert body["schedule"] == "DAILY"
        assert body["dry_run"] is True
        assert "next_run_at" in body

    def test_policies_endpoint(self, db_manager):
        client = self._build_client(db_manager)
        response = client.get("/api/v1/retention/policies")
        assert response.status_code == 200
        policies = response.json()["policies"]
        assert any(policy["policy_id"] == "trace_events" for policy in policies)

    def test_preview_endpoint_is_dry_run(self, db_manager):
        client = self._build_client(db_manager)
        response = client.post("/api/v1/retention/preview")
        assert response.status_code == 200
        assert response.json()["dry_run"] is True

    def test_run_endpoint_requires_confirmation(self, db_manager):
        client = self._build_client(db_manager)
        response = client.post("/api/v1/retention/run", json={"confirm": False})
        assert response.status_code == 400

        response = client.post("/api/v1/retention/run", json={"confirm": True})
        assert response.status_code == 200
        body = response.json()
        assert body["trigger"] == "MANUAL"

    def test_run_history_lists_runs(self, db_manager):
        client = self._build_client(db_manager)
        client.post("/api/v1/retention/preview")
        response = client.get("/api/v1/retention/runs", params={"limit": 5})
        assert response.status_code == 200
        assert len(response.json()["runs"]) >= 1

    def test_update_policy_confirmation_flow(self, db_manager):
        client = self._build_client(db_manager)

        conflict = client.patch(
            "/api/v1/retention/policies/trace_events",
            json={"retention_period": "30d"},
        )
        assert conflict.status_code == 409

        ok = client.patch(
            "/api/v1/retention/policies/trace_events",
            json={"retention_period": "30d", "confirm": True, "actor": "tester"},
        )
        assert ok.status_code == 200
        assert ok.json()["retention_period"] == "30d"

    def test_update_unknown_policy(self, db_manager):
        client = self._build_client(db_manager)
        response = client.patch(
            "/api/v1/retention/policies/missing",
            json={"enabled": False},
        )
        assert response.status_code == 404
