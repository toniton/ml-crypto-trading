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

_TEST_CONFIG_DIR = tempfile.mkdtemp(prefix="orders-api-tests-")
_TEST_CONFIG_PATH = os.path.join(_TEST_CONFIG_DIR, "trading-config.yaml")
with open(_TEST_CONFIG_PATH, "w", encoding="utf-8") as handle:
    handle.write(SAMPLE_CONFIG)


def build_app(db_manager):
    return ChatApp.create(
        agent=AgentGateway(FakeLlmAdapter(chunks=["ok"]), _TEST_CONFIG_PATH),
        event_bus=MessageEventBus(),
        db_manager=db_manager,
    )


class TestOrdersEndpoint(unittest.TestCase):
    def test_returns_orders_for_day(self):
        db_manager = MagicMock(spec=DatabaseManager)
        payload = {
            "date": "2026-08-08",
            "count": 1,
            "orders": [
                {
                    "uuid": "u1",
                    "ticker_symbol": "BTC_USD",
                    "provider_name": "CRYPTO_DOT_COM",
                    "trade_action": "BUY",
                    "price": "42500.50",
                    "quantity": "0.00005",
                    "status": "COMPLETED",
                    "created_time": 1754697600.0,
                }
            ],
        }
        service = MagicMock()
        service.for_date.return_value = payload
        with patch("src.server.app.OrderByDayService", MagicMock(return_value=service)):
            client = TestClient(build_app(db_manager))
            response = client.get("/api/v1/orders/2026/8/8")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["date"], "2026-08-08")
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["orders"][0]["trade_action"], "BUY")

    def test_returns_week_counts(self):
        db_manager = MagicMock(spec=DatabaseManager)
        payload = {
            "start": "2026-08-03",
            "end": "2026-08-09",
            "days": [{"date": "2026-08-08", "count": 3}],
        }
        service = MagicMock()
        service.for_week.return_value = payload
        with patch("src.server.app.OrderWeekService", MagicMock(return_value=service)):
            client = TestClient(build_app(db_manager))
            response = client.get("/api/v1/orders/week/2026/8/8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["days"][0]["count"], 3)

    def test_invalid_date_returns_422(self):
        db_manager = MagicMock(spec=DatabaseManager)
        client = TestClient(build_app(db_manager))
        response = client.get("/api/v1/orders/2026/2/30")
        self.assertEqual(response.status_code, 422)
        self.assertIn("Invalid date", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
