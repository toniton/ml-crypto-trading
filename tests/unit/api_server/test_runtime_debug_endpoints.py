from datetime import datetime, timezone
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
import yaml

from src.agent import AgentGateway
from src.agent.runtime_debug.models import (
    ErrorCategory,
    ErrorSeverity,
    IncidentStatus,
    RuntimeErrorEvent,
    RuntimeIncident,
)
from src.configuration.trading_config import TradingConfig
from src.database.repositories.providers.postgres_runtime_incident_repository import (
    PostgresRuntimeIncidentRepository,
)
from src.events.message_event_bus import MessageEventBus
from src.recorder.market_data_store import MarketDataStore
from src.server.app import ChatApp
from src.vcs.application.service import VCSService
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
    consensus:
      buy: 1.3
      sell: 0.5
"""


class TestRuntimeDebugEndpoints(unittest.TestCase):
    def setUp(self):
        self.db_manager = make_temp_db_manager()
        self.vcs = VCSService(self.db_manager)
        self.vcs.seed_if_empty(
            TradingConfig.model_validate(yaml.safe_load(SAMPLE_CONFIG)),
            author="test",
            message="seed",
        )
        self.llm = FakeLlmAdapter(chunks=["ok"])
        self.gateway = AgentGateway(self.llm, vcs=self.vcs)
        self.app = ChatApp.create(
            agent=self.gateway,
            event_bus=MessageEventBus(),
            db_manager=self.db_manager,
            market_data_store=MarketDataStore(),
            vcs=self.vcs,
        )
        self.client = TestClient(self.app)

        # Seed an incident with an error event
        self.incident_id = uuid4()
        with self.db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresRuntimeIncidentRepository)
            incident = RuntimeIncident(
                id=self.incident_id,
                fingerprint="fp-api-test",
                status=IncidentStatus.DETECTED,
                category=ErrorCategory.EXCHANGE_VALIDATION,
                severity=ErrorSeverity.CRITICAL,
                component="trading.orders.order_manager",
                asset="BTC_USD",
                exchange="CRYPTO_DOT_COM",
                first_seen=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
                occurrence_count=3,
            )
            repo.save(incident)

            error_event = RuntimeErrorEvent(
                id=uuid4(),
                incident_id=self.incident_id,
                severity=ErrorSeverity.CRITICAL,
                component="trading.orders.order_manager",
                error_type="RuntimeError",
                message="Invalid quantity format: 0.000078",
                asset="BTC_USD",
                exchange="CRYPTO_DOT_COM",
                exchange_code=213,
                metadata={"order_quantity": "0.000078"},
                fingerprint="fp-api-test",
            )
            repo.add_error_event(error_event)

    def test_list_incidents(self):
        response = self.client.get("/api/v1/runtime/incidents")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("incidents", data)
        self.assertEqual(len(data["incidents"]), 1)
        self.assertEqual(data["incidents"][0]["id"], str(self.incident_id))

    def test_list_active_incidents(self):
        response = self.client.get("/api/v1/runtime/incidents/active")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("active_incidents", data)
        self.assertEqual(len(data["active_incidents"]), 1)

    def test_get_incident_detail(self):
        response = self.client.get(f"/api/v1/runtime/incidents/{self.incident_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], str(self.incident_id))
        self.assertEqual(len(data["events"]), 1)
        self.assertEqual(data["events"][0]["exchange_code"], 213)

    def test_investigate_incident(self):
        response = self.client.post(f"/api/v1/runtime/incidents/{self.incident_id}/investigate")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNotNone(data.get("diagnosis"))
        self.assertIsNotNone(data.get("suggestion"))
        self.assertEqual(data["incident"]["status"], IncidentStatus.SUGGESTION_READY.value)

    def test_acknowledge_and_resolve_lifecycle(self):
        ack_res = self.client.post(
            f"/api/v1/runtime/incidents/{self.incident_id}/acknowledge",
            json={"notes": "Investigating by operator"},
        )
        self.assertEqual(ack_res.status_code, 200)
        self.assertEqual(ack_res.json()["new_status"], IncidentStatus.ACKNOWLEDGED.value)

        resolve_res = self.client.post(
            f"/api/v1/runtime/incidents/{self.incident_id}/resolve",
            json={"notes": "Fixed precision in code"},
        )
        self.assertEqual(resolve_res.status_code, 200)
        self.assertEqual(resolve_res.json()["new_status"], IncidentStatus.RESOLVED.value)
