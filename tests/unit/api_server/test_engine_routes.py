import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.core.interfaces.trading_engine_proxy import (
    AssetRuntimeSnapshot,
    EngineStatus,
    TradingEngineProxy,
)
from src.server.app import ChatApp


class TestEngineRoutes(unittest.TestCase):
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

    def test_get_engine_status(self):
        self.mock_proxy.get_status.return_value = EngineStatus(
            is_running=True,
            state="RUNNING",
            monitored_assets=["BTC_USD", "ETH_USD"],
            asset_count=2,
        )
        response = self.client.get("/api/v1/engine/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["is_running"])
        self.assertEqual(data["state"], "RUNNING")
        self.assertEqual(data["monitored_assets"], ["BTC_USD", "ETH_USD"])
        self.assertEqual(data["asset_count"], 2)

    def test_list_monitored_assets(self):
        self.mock_proxy.list_monitored_assets.return_value = ["BTC_USD", "SOL_USD"]
        response = self.client.get("/api/v1/engine/assets")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["BTC_USD", "SOL_USD"])

    def test_get_asset_snapshot_found(self):
        self.mock_proxy.get_asset_snapshot.return_value = AssetRuntimeSnapshot(
            ticker_symbol="BTC_USD",
            active_strategies=["Momentum"],
            open_orders_count=1,
            total_trades_count=5,
            position_quantity=0.5,
            latest_price=64000.0,
        )
        response = self.client.get("/api/v1/engine/assets/BTC_USD")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["ticker_symbol"], "BTC_USD")
        self.assertEqual(data["open_orders_count"], 1)
        self.assertEqual(data["latest_price"], 64000.0)

    def test_get_asset_snapshot_not_found(self):
        self.mock_proxy.get_asset_snapshot.return_value = None
        response = self.client.get("/api/v1/engine/assets/UNKNOWN")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not currently monitored", response.json()["detail"])
