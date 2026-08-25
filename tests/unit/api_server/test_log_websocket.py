import logging
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.agent import AgentGateway
from src.database.database_manager import DatabaseManager
from src.events.message_event_bus import MessageEventBus
from src.logging.log_event import LogEvent, LogEventPayload
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

_TEST_CONFIG_DIR = tempfile.mkdtemp(prefix="log-ws-tests-")
_TEST_CONFIG_PATH = os.path.join(_TEST_CONFIG_DIR, "trading-config.yaml")
with open(_TEST_CONFIG_PATH, "w", encoding="utf-8") as handle:
    handle.write(SAMPLE_CONFIG)


def make_event(domain="trading", levelno=logging.INFO, asset=None, message="hello"):
    return LogEvent(
        LogEventPayload(
            domain=domain,
            level="INFO" if levelno == logging.INFO else "ERROR",
            level_no=levelno,
            logger=f"{domain}.test",
            message=message,
            asset=asset,
        )
    )


def build_client(bus):
    app = ChatApp.create(
        agent=AgentGateway(FakeLlmAdapter(chunks=["ok"]), _TEST_CONFIG_PATH),
        event_bus=bus,
        db_manager=MagicMock(spec=DatabaseManager),
    )
    return TestClient(app)


class TestLogWebSocket(unittest.TestCase):
    def test_connected_event(self):
        bus = MessageEventBus()
        client = build_client(bus)
        with client.websocket_connect("/api/v1/logs/ws") as ws:
            data = ws.receive_json()
            self.assertEqual(data["type"], "connected")
            self.assertTrue(data["timestamp"])

    def test_live_event_delivered(self):
        bus = MessageEventBus()
        client = build_client(bus)
        with client.websocket_connect("/api/v1/logs/ws") as ws:
            ws.receive_json()
            bus.publish(make_event(message="Consensus reached"))
            data = ws.receive_json()
            self.assertEqual(data["type"], "log")
            self.assertEqual(data["payload"]["message"], "Consensus reached")
            self.assertTrue(data["id"])

    def test_unsubscribe_on_disconnect(self):
        bus = MessageEventBus()
        client = build_client(bus)
        self.assertEqual(bus.subscriber_count(), 0)
        with client.websocket_connect("/api/v1/logs/ws") as ws:
            ws.receive_json()
            self.assertEqual(bus.subscriber_count(), 1)
        self.assertEqual(bus.subscriber_count(), 0)

    def test_concurrent_subscribers(self):
        bus = MessageEventBus()
        client = build_client(bus)
        with client.websocket_connect("/api/v1/logs/ws") as ws1, client.websocket_connect(
            "/api/v1/logs/ws"
        ) as ws2:
            ws1.receive_json()
            ws2.receive_json()
            bus.publish(make_event(message="broadcast"))
            self.assertEqual(ws1.receive_json()["payload"]["message"], "broadcast")
            self.assertEqual(ws2.receive_json()["payload"]["message"], "broadcast")


if __name__ == "__main__":
    unittest.main()
