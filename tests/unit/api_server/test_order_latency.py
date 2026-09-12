import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.agent import AgentGateway
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.events.message_event_bus import MessageEventBus
from src.recorder.market_data_store import MarketDataStore
from src.server.app import ChatApp
from src.vcs.application.service import VCSService
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


def build_app(db_manager):
    vcs = MagicMock(spec=VCSService)
    return ChatApp.create(
        agent=AgentGateway(FakeLlmAdapter(chunks=["ok"]), vcs=vcs),
        event_bus=MessageEventBus(),
        db_manager=db_manager,
        market_data_store=MarketDataStore(),
        vcs=vcs,
    )


class TestOrderLatencyEndpoint(unittest.TestCase):
    def test_returns_day_latency_stats(self):
        db_manager = MagicMock(spec=SqlAlchemyDatabaseManager)
        payload = {
            "year": 2026,
            "month": 8,
            "start": "2026-08-01",
            "end": "2026-08-31",
            "days": [
                {"date": "2026-08-25", "count": 2, "avg_ms": 730.5, "min_ms": 684.0, "max_ms": 777.0},
                {"date": "2026-08-26", "count": 0, "avg_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0},
            ],
        }
        service = MagicMock()
        service.for_month.return_value = payload
        with patch("src.server.app.OrderLatencyService", MagicMock(return_value=service)):
            client = TestClient(build_app(db_manager))
            response = client.get("/api/v1/orders/latency/2026/8")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["start"], "2026-08-01")
        self.assertEqual(data["end"], "2026-08-31")
        self.assertEqual(data["days"][0]["avg_ms"], 730.5)
        self.assertEqual(data["days"][0]["count"], 2)

    def test_invalid_month_returns_422(self):
        db_manager = MagicMock(spec=SqlAlchemyDatabaseManager)
        client = TestClient(build_app(db_manager))
        response = client.get("/api/v1/orders/latency/2026/13")
        self.assertEqual(response.status_code, 422)
        self.assertIn("month", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
