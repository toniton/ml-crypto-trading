from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.agent import AgentGateway
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.events.agent_events import (
    AgentApprovalRequestedEvent,
    AgentMessageCreatedEvent,
    TradingActivityAnomalyDetectedEvent,
)
from src.events.message_event_bus import MessageEventBus
from src.recorder.market_data_store import MarketDataStore
from src.server.app import ChatApp
from src.vcs.application.service import VCSService
from tests.unit.agent.fakes import FakeLlmAdapter


def build_client(bus: MessageEventBus) -> TestClient:
    db_mgr = MagicMock(spec=SqlAlchemyDatabaseManager)
    vcs = MagicMock(spec=VCSService)
    app = ChatApp.create(
        agent=AgentGateway(FakeLlmAdapter(chunks=["ok"]), vcs=vcs),
        event_bus=bus,
        db_manager=db_mgr,
        market_data_store=MarketDataStore(),
        vcs=vcs,
    )
    return TestClient(app)


class TestAgentWebSocket(unittest.TestCase):
    def test_connected_event(self):
        bus = MessageEventBus()
        client = build_client(bus)
        with client.websocket_connect("/api/v1/agent/ws") as ws:
            data = ws.receive_json()
            self.assertEqual(data["type"], "connected")
            self.assertEqual(data["channel"], "agent")
            self.assertTrue(data["timestamp"])

    def test_approval_requested_event_delivered_safely(self):
        bus = MessageEventBus()
        client = build_client(bus)
        with client.websocket_connect("/api/v1/agent/ws") as ws:
            ws.receive_json()  # consume connected message
            event = AgentApprovalRequestedEvent(
                approval_id="ap-cro-pause",
                approval_payload={
                    "approval_id": "ap-cro-pause",
                    "agent_action_id": "act-1",
                    "title": "Pause CRO_USD",
                    "description": "Proposal to pause starved asset CRO_USD.",
                    "base_commit": "abcdef123456",
                    "asset": "CRO_USD",
                    "proposed_change": {"changes": []},
                    "status": "pending",
                },
            )
            bus.publish(event)
            data = ws.receive_json()
            self.assertEqual(data["event_name"], "agent_approval_requested")
            self.assertEqual(data["approval_id"], "ap-cro-pause")
            self.assertEqual(data["approval_payload"]["title"], "Pause CRO_USD")

    def test_anomaly_and_message_events_delivered(self):
        bus = MessageEventBus()
        client = build_client(bus)
        with client.websocket_connect("/api/v1/agent/ws") as ws:
            ws.receive_json()
            anomaly_event = TradingActivityAnomalyDetectedEvent(
                asset="CRO_USD",
                anomaly_kind="NO_MARKET_DATA",
                threshold=63.0,
            )
            bus.publish(anomaly_event)
            data = ws.receive_json()
            self.assertEqual(data["event_name"], "trading_activity_anomaly_detected")
            self.assertEqual(data["asset"], "CRO_USD")

            msg_event = AgentMessageCreatedEvent(
                conversation_id="sess-cro",
                message_payload={"content": "CRO diagnostic summary", "blocks": []},
            )
            bus.publish(msg_event)
            msg_data = ws.receive_json()
            self.assertEqual(msg_data["event_name"], "agent_message_created")
            self.assertEqual(msg_data["conversation_id"], "sess-cro")

    def test_unsubscribe_on_disconnect(self):
        bus = MessageEventBus()
        client = build_client(bus)
        baseline = bus.subscriber_count()
        with client.websocket_connect("/api/v1/agent/ws") as ws:
            ws.receive_json()
            self.assertGreater(bus.subscriber_count(), baseline)
        self.assertEqual(bus.subscriber_count(), baseline)


if __name__ == "__main__":
    unittest.main()
