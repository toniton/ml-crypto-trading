import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from src.agent import AgentGateway
from src.events.message_event_bus import MessageEventBus
from src.server.app import ChatApp
from tests.unit.agent.fakes import FakeLlmAdapter
from tests.unit.api_server.helpers import make_temp_db_manager

SAMPLE_CONFIG = """
assets:
  - name: "Bitcoin"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 0.00005
    quote_decimals: 2
    quantity_decimals: 5
    candles_timeframe: "MIN1"
    schedule: 1
    guard_config:
      max_drawdown_period: 8
      max_drawdown_percentage: 0.60
      cooldown_timeout: 5
    strategies:
      - name: "RsiBuy"
        type: "DYNAMIC"
        action: "BUY"
        expression: "rsi(14) < 30"
    consensus:
      buy: 1.3
      sell: 0.5
dynamic_quantity: "max(min_qty, 1.0)"
"""


class TestConfigEndpoints(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="config-test-")
        self.config_path = os.path.join(self.temp_dir, "trading-config.yaml")
        with open(self.config_path, "w", encoding="utf-8") as handle:
            handle.write(SAMPLE_CONFIG)

        self.db = make_temp_db_manager()
        self.agent = AgentGateway(FakeLlmAdapter(), self.config_path)
        self.app = ChatApp.create(
            agent=self.agent,
            event_bus=MessageEventBus(),
            db_manager=self.db,
        )
        self.client = TestClient(self.app)

    def test_get_config_returns_assets_and_dynamic_quantity(self):
        response = self.client.get("/api/v1/config")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("assets", data)
        self.assertIn("dynamic_quantity", data)
        self.assertEqual(len(data["assets"]), 1)
        self.assertEqual(data["assets"][0]["base_ticker_symbol"], "BTC")
        self.assertEqual(data["dynamic_quantity"], "max(min_qty, 1.0)")

    def test_get_config_options_returns_exchanges_timeframes_and_schedules(self):
        response = self.client.get("/api/v1/config/options")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("exchanges", data)
        self.assertIn("timeframes", data)
        self.assertIn("schedules", data)
        self.assertIn("CRYPTO_DOT_COM", data["exchanges"])
        self.assertIn("MIN1", data["timeframes"])
        self.assertTrue(any(s["value"] == 1 and "Minute" in s["label"] for s in data["schedules"]))

    def test_post_config_commits_and_updates_head(self):
        payload = {
            "assets": [
                {
                    "name": "Ethereum",
                    "base_ticker_symbol": "ETH",
                    "quote_ticker_symbol": "USD",
                    "exchange": "CRYPTO_DOT_COM",
                    "min_quantity": 0.01,
                    "quote_decimals": 2,
                    "quantity_decimals": 4,
                    "candles_timeframe": "MIN1",
                    "schedule": 1,
                    "consensus": {"buy": 1.5, "sell": 0.5},
                    "strategies": [],
                }
            ],
            "dynamic_quantity": "equity * 0.05",
            "message": "Add Ethereum config",
            "author": "tester",
        }
        post_res = self.client.post("/api/v1/config", json=payload)
        self.assertEqual(post_res.status_code, 200)
        post_data = post_res.json()
        self.assertEqual(post_data["status"], "committed")
        self.assertEqual(post_data["summary"], "Add Ethereum config")
        self.assertTrue(bool(post_data["commit_hash"]))

        get_res = self.client.get("/api/v1/config")
        self.assertEqual(get_res.status_code, 200)
        get_data = get_res.json()
        self.assertEqual(len(get_data["assets"]), 1)
        self.assertEqual(get_data["assets"][0]["base_ticker_symbol"], "ETH")
        self.assertEqual(get_data["dynamic_quantity"], "equity * 0.05")
        self.assertEqual(get_data["commit_hash"], post_data["commit_hash"])

    def test_post_config_validation_failure_returns_422(self):
        invalid_payload = {
            "assets": [
                {
                    "name": "InvalidAsset",
                    "base_ticker_symbol": "INV",
                    "quote_ticker_symbol": "USD",
                    "exchange": "CRYPTO_DOT_COM",
                    "min_quantity": -5.0,
                    "quote_decimals": 2,
                    "quantity_decimals": 2,
                    "candles_timeframe": "MIN1",
                    "schedule": 1,
                }
            ],
        }
        res = self.client.post("/api/v1/config", json=invalid_payload)
        self.assertEqual(res.status_code, 422)
