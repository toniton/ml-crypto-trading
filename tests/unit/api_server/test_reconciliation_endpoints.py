import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.core.interfaces.trading_engine_proxy import TradingEngineProxy
from src.server.app import ChatApp


class TestReconciliationEndpoints(unittest.TestCase):
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

    def test_get_reconciliation_status(self):
        self.mock_proxy.get_reconciliation_status.return_value = {
            "has_unresolved_discrepancies": True,
            "discrepancy_count": 1,
            "discrepancies": [{"type": "POSITION_MISMATCH", "symbol": "CRO_USD"}],
        }
        response = self.client.get("/api/v1/reconciliation/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["has_unresolved_discrepancies"])
        self.assertEqual(data["discrepancy_count"], 1)

    def test_get_discrepancies(self):
        self.mock_proxy.get_reconciliation_status.return_value = {
            "discrepancies": [{"type": "BALANCE_MISMATCH", "symbol": "USD"}]
        }
        response = self.client.get("/api/v1/reconciliation/discrepancies")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"type": "BALANCE_MISMATCH", "symbol": "USD"}])

    def test_trigger_reconciliation(self):
        self.mock_proxy.trigger_reconciliation.return_value = True
        response = self.client.post("/api/v1/reconciliation/trigger")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"triggered": True})
        self.mock_proxy.trigger_reconciliation.assert_called_once()

    def test_clear_discrepancies(self):
        self.mock_proxy.clear_reconciliation_discrepancies.return_value = True
        response = self.client.post("/api/v1/reconciliation/clear")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"cleared": True})
        self.mock_proxy.clear_reconciliation_discrepancies.assert_called_once()
