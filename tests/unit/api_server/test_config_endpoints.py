import unittest
from unittest.mock import MagicMock

import yaml
from fastapi.testclient import TestClient

from src.agent import AgentGateway
from src.configuration.trading_config import TradingConfig
from src.events.message_event_bus import MessageEventBus
from src.server.app import ChatApp
from src.vcs.application.service import VCSService
from tests.unit.agent.fakes import FakeLlmAdapter
from tests.unit.api_server.helpers import (
    make_temp_db_manager,
    make_test_llm_manager,
    make_test_trading_proxy,
)

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
        self.db = make_temp_db_manager()
        self.vcs = VCSService(self.db)
        self.vcs.seed_if_empty(
            TradingConfig.model_validate(yaml.safe_load(SAMPLE_CONFIG)),
            author="test",
            message="seed",
        )
        self.agent = AgentGateway(FakeLlmAdapter(), vcs=self.vcs)
        self.mock_trading_engine = MagicMock()
        self.trading_proxy = make_test_trading_proxy(trading_engine=self.mock_trading_engine)
        self.app = ChatApp.create(
            trading_proxy=self.trading_proxy,
            agent=self.agent,
            event_bus=MessageEventBus(),
            db_manager=self.db,
            vcs=self.vcs,
            llm_manager=make_test_llm_manager(self.db),
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
        self.mock_trading_engine.update_config.assert_called()
        updated_trading_config = self.mock_trading_engine.update_config.call_args[0][0]
        self.assertEqual(updated_trading_config.assets[0].base_ticker_symbol, "ETH")

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

    def test_post_and_get_portfolio_config(self):
        payload = {
            "assets": [
                {
                    "name": "Bitcoin",
                    "base_ticker_symbol": "BTC",
                    "quote_ticker_symbol": "USD",
                    "exchange": "CRYPTO_DOT_COM",
                    "min_quantity": 0.00005,
                    "quote_decimals": 2,
                    "quantity_decimals": 5,
                    "candles_timeframe": "MIN1",
                    "schedule": 1,
                    "portfolio": {
                        "exposure": {
                            "max_per_asset": 0.35,
                        },
                    },
                }
            ],
            "portfolio": {
                "exposure": {
                    "max_total": 0.70,
                    "max_per_asset": 0.20,
                    "max_per_quote": 0.40,
                },
                "guard": {
                    "min_quote_reserve": 0.15,
                },
            },
            "message": "Update global portfolio and asset override",
            "author": "tester",
        }
        post_res = self.client.post("/api/v1/config", json=payload)
        self.assertEqual(post_res.status_code, 200)

        get_res = self.client.get("/api/v1/config")
        self.assertEqual(get_res.status_code, 200)
        data = get_res.json()
        self.assertIn("portfolio", data)
        self.assertEqual(float(data["portfolio"]["exposure"]["max_total"]), 0.70)
        self.assertEqual(float(data["portfolio"]["guard"]["min_quote_reserve"]), 0.15)
        self.assertEqual(float(data["assets"][0]["portfolio"]["exposure"]["max_per_asset"]), 0.35)

    def test_post_portfolio_camel_case(self):
        payload = {
            "assets": [
                {
                    "name": "Bitcoin",
                    "base_ticker_symbol": "BTC",
                    "quote_ticker_symbol": "USD",
                    "exchange": "CRYPTO_DOT_COM",
                    "min_quantity": 0.00005,
                    "quote_decimals": 2,
                    "quantity_decimals": 5,
                    "candles_timeframe": "MIN1",
                    "schedule": 1,
                    "portfolio": {
                        "exposure": {
                            "maxPerAsset": 0.40,
                        },
                    },
                }
            ],
            "portfolio": {
                "exposure": {
                    "maxTotal": 0.85,
                    "maxPerAsset": 0.30,
                    "maxPerQuote": 0.60,
                },
                "guard": {
                    "minQuoteReserve": 0.20,
                },
            },
            "message": "Update global portfolio with camelCase",
            "author": "tester",
        }
        post_res = self.client.post("/api/v1/config", json=payload)
        self.assertEqual(post_res.status_code, 200)

        get_res = self.client.get("/api/v1/config")
        self.assertEqual(get_res.status_code, 200)
        data = get_res.json()
        self.assertEqual(float(data["portfolio"]["exposure"]["max_total"]), 0.85)
        self.assertEqual(float(data["portfolio"]["guard"]["min_quote_reserve"]), 0.20)
        self.assertEqual(float(data["assets"][0]["portfolio"]["exposure"]["max_per_asset"]), 0.40)
