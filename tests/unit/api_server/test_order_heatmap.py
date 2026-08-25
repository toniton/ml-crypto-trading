import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.agent import AgentGateway
from src.database.database_manager import DatabaseManager
from src.events.message_event_bus import MessageEventBus
from src.server.app import ChatApp
from tests.unit.agent.fakes import FakeLlmAdapter

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
    consensus:
      buy: 1.3
      sell: 0.5
"""

_TEST_CONFIG_DIR = tempfile.mkdtemp(prefix="heatmap-api-tests-")
_TEST_CONFIG_PATH = os.path.join(_TEST_CONFIG_DIR, "trading-config.yaml")
with open(_TEST_CONFIG_PATH, "w", encoding="utf-8") as handle:
    handle.write(SAMPLE_CONFIG)


def build_app(db_manager):
    return ChatApp.create(
        agent=AgentGateway(FakeLlmAdapter(chunks=["ok"]), _TEST_CONFIG_PATH),
        event_bus=MessageEventBus(),
        db_manager=db_manager,
    )


class TestOrderHeatmapEndpoint(unittest.TestCase):
    def test_returns_day_counts(self):
        db_manager = MagicMock(spec=DatabaseManager)
        payload = {
            "year": 2026,
            "month": 10,
            "start": "2026-08-01",
            "end": "2026-10-31",
            "days": [
                {"date": "2026-08-01", "buy": 2, "sell": 1, "total": 3},
                {"date": "2026-08-02", "buy": 0, "sell": 0, "total": 0},
            ],
        }
        service = MagicMock()
        service.daily_counts.return_value = payload
        with patch("src.server.app.OrderHeatmapService", MagicMock(return_value=service)):
            client = TestClient(build_app(db_manager))
            response = client.get("/api/v1/heatmap/orders/2026/10")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["year"], 2026)
        self.assertEqual(data["month"], 10)
        self.assertEqual(data["start"], "2026-08-01")
        self.assertEqual(data["end"], "2026-10-31")
        self.assertEqual(data["days"][0]["date"], "2026-08-01")
        self.assertEqual(data["days"][0]["total"], 3)

    def test_invalid_month_returns_422(self):
        db_manager = MagicMock(spec=DatabaseManager)
        client = TestClient(build_app(db_manager))
        response = client.get("/api/v1/heatmap/orders/2026/13")
        self.assertEqual(response.status_code, 422)
        self.assertIn("month", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
