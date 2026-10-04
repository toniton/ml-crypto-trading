import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.core.interfaces.trading_engine_proxy import TradingEngineProxy
from src.server.app import ChatApp


class TestHealthRoutes(unittest.TestCase):
    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_event_bus = MagicMock()
        self.mock_db = MagicMock()
        self.mock_vcs = MagicMock()
        self.mock_proxy = MagicMock(spec=TradingEngineProxy)
        self.mock_llm_manager = MagicMock()

        self.app = ChatApp.create(
            trading_proxy=self.mock_proxy,
            agent=self.mock_agent,
            event_bus=self.mock_event_bus,
            db_manager=self.mock_db,
            vcs=self.mock_vcs,
            llm_manager=self.mock_llm_manager,
        )
        self.client = TestClient(self.app)

    def test_get_health_snapshot_success(self):
        self.mock_proxy.get_health_snapshot.return_value = {
            "state": "TRADING",
            "version": 3,
            "effective_permissions": ["new_orders", "cancel_orders"],
            "active_conditions": [],
            "updated_at": "2026-10-04T10:00:00Z",
        }
        response = self.client.get("/api/v1/trading/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "TRADING")
        self.assertEqual(data["version"], 3)
        self.assertIn("new_orders", data["effective_permissions"])

    def test_get_health_snapshot_not_found(self):
        self.mock_proxy.get_health_snapshot.return_value = None
        response = self.client.get("/api/v1/trading/health")
        self.assertEqual(response.status_code, 404)

    def test_pause_trading(self):
        self.mock_proxy.pause_trading.return_value = {
            "state": "PAUSED",
            "version": 4,
            "effective_permissions": ["cancel_orders"],
            "active_conditions": [],
            "updated_at": "2026-10-04T10:00:05Z",
        }
        response = self.client.post("/api/v1/trading/health/pause")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "PAUSED")

    def test_resume_trading(self):
        self.mock_proxy.resume_trading.return_value = {
            "state": "RECOVERING",
            "version": 5,
            "effective_permissions": ["cancel_orders"],
            "active_conditions": [],
            "updated_at": "2026-10-04T10:00:10Z",
        }
        response = self.client.post("/api/v1/trading/health/resume")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "RECOVERING")
