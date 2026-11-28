import unittest
from datetime import datetime, timezone
from uuid import uuid4

import yaml
from fastapi.testclient import TestClient

from src.agent import AgentGateway
from src.agent.runtime_debug.models import (
    ErrorCategory,
    IncidentStatus,
    RuntimeErrorEvent,
    RuntimeIncident,
)
from src.configuration.trading_config import TradingConfig
from src.core.severity import Severity
from src.database.repositories.providers.postgres_runtime_incident_repository import (
    PostgresRuntimeIncidentRepository,
)
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
        from src.retention.manager import RetentionManager
        self.app = ChatApp.create(
            trading_proxy=make_test_trading_proxy(),
            agent=self.gateway,
            event_bus=MessageEventBus(),
            db_manager=self.db_manager,
            vcs=self.vcs,
            llm_manager=make_test_llm_manager(self.db_manager),
            retention_manager=RetentionManager(self.db_manager),
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
                severity=Severity.CRITICAL,
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
                severity=Severity.CRITICAL,
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

    def test_exchange_constraints_and_propose_fix_routes_for_cro_below_min_order_size(self):
        from decimal import Decimal
        from unittest.mock import MagicMock
        from api.interfaces.instrument_metadata import InstrumentMetadata
        from src.agent.actions.service import AgentActionService, AgentApprovalService
        from src.agent.configuration.configuration_service import ConfigurationService
        from src.agent.runtime_debug.models import DebugSuggestion, RiskLevel
        from src.agent.runtime_debug.service import RuntimeDebugService
        from src.retention.manager import RetentionManager

        cro_config = """
assets:
  - name: "Cronos"
    base_ticker_symbol: "CRO"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 19.0
    quote_decimals: 5
    quantity_decimals: 0
    candles_timeframe: "MIN1"
    schedule: 1
    consensus:
      buy: 0.7
      sell: 0.4
"""
        db_manager = make_temp_db_manager()
        vcs = VCSService(db_manager)
        vcs.seed_if_empty(
            TradingConfig.model_validate(yaml.safe_load(cro_config)),
            author="test",
            message="seed cro",
        )
        event_bus = MessageEventBus()
        action_service = AgentActionService(event_bus=event_bus)
        approval_service = AgentApprovalService(
            vcs=vcs,
            configuration_service=ConfigurationService(vcs=vcs),
            action_service=action_service,
            event_bus=event_bus,
        )
        rest_manager = MagicMock()
        rest_manager.get_instrument_metadata.return_value = InstrumentMetadata(
            exchange="CRYPTO_DOT_COM",
            symbol="CRO_USD",
            quantity_precision=0,
            price_precision=5,
            min_quantity=Decimal("1"),
            quantity_step=Decimal("1"),
            min_price=Decimal("0.00001"),
            min_notional=Decimal("1.00"),
        )
        shared_debug_service = RuntimeDebugService(
            database_manager=db_manager,
            vcs=vcs,
            event_bus=event_bus,
            rest_manager=rest_manager,
            agent_event_bus=event_bus,
            action_service=action_service,
            approval_service=approval_service,
        )
        app = ChatApp.create(
            trading_proxy=make_test_trading_proxy(),
            agent=AgentGateway(FakeLlmAdapter(chunks=["ok"]), vcs=vcs),
            event_bus=event_bus,
            db_manager=db_manager,
            vcs=vcs,
            llm_manager=make_test_llm_manager(db_manager),
            retention_manager=RetentionManager(db_manager),
            runtime_debug_service=shared_debug_service,
        )
        client = TestClient(app)

        cro_incident_id = uuid4()
        with db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresRuntimeIncidentRepository)
            repo.save(
                RuntimeIncident(
                    id=cro_incident_id,
                    fingerprint="fp-cro-min-size",
                    status=IncidentStatus.ACKNOWLEDGED,
                    category=ErrorCategory.EXCHANGE_VALIDATION,
                    severity=Severity.CRITICAL,
                    component="trading.orders.order_manager",
                    operation="execute_order",
                    asset="CRO_USD",
                    exchange="CRYPTO_DOT_COM",
                    first_seen=datetime.now(timezone.utc),
                    last_seen=datetime.now(timezone.utc),
                    occurrence_count=100,
                    suggestion=DebugSuggestion(
                        summary="Runtime error: BELOW_MIN_ORDER_SIZE",
                        root_cause="Runtime execution failure.",
                        affected_component="trading.orders.order_manager",
                        proposed_change="Review error stack trace.",
                        rationale="Manual review recommended.",
                        risk=RiskLevel.MEDIUM,
                        requires_code_change=True,
                        requires_configuration_change=False,
                    ),
                )
            )
            repo.add_error_event(
                RuntimeErrorEvent(
                    id=uuid4(),
                    incident_id=cro_incident_id,
                    severity=Severity.CRITICAL,
                    component="trading.orders.order_manager",
                    operation="execute_order",
                    error_type="RuntimeError",
                    message="BELOW_MIN_ORDER_SIZE",
                    asset="CRO_USD",
                    exchange="CRYPTO_DOT_COM",
                    exchange_code=415,
                    http_status=500,
                    metadata={"order_quantity": "19", "order_price": "0.039990"},
                    fingerprint="fp-cro-min-size",
                )
            )

        # 1. Exchange constraints route returns live metadata + current VCS min_quantity
        meta_res = client.get("/api/v1/runtime/exchange/CRYPTO_DOT_COM/instruments/CRO_USD")
        self.assertEqual(meta_res.status_code, 200)
        meta_data = meta_res.json()
        self.assertEqual(meta_data["source"], "exchange_api")
        self.assertEqual(meta_data["min_notional"], "1.00")
        self.assertEqual(meta_data["current_min_quantity"], 19.0)

        # 2. Propose-fix route generates a deduplicated approval request raising 19 -> 26
        fix_res = client.post(f"/api/v1/runtime/incidents/{cro_incident_id}/propose-fix")
        self.assertEqual(fix_res.status_code, 200)
        fix_data = fix_res.json()
        self.assertIsNotNone(fix_data["approval_request"])
        changes = fix_data["approval_request"]["proposed_change"]["changes"]
        self.assertEqual(changes[0]["path"], "assets.CRO_USD.min_quantity")
        self.assertEqual(changes[0]["old_value"], 19.0)
        self.assertEqual(changes[0]["new_value"], 26.0)

        # 3. Calling propose-fix again deduplicates to the existing pending approval
        fix_res_2 = client.post(f"/api/v1/runtime/incidents/{cro_incident_id}/propose-fix")
        self.assertEqual(fix_res_2.status_code, 200)
        self.assertEqual(
            fix_res_2.json()["approval_request"]["id"],
            fix_data["approval_request"]["id"],
        )

    def test_sweep_critical_incidents_picks_up_acknowledged_exchange_validation_incident(self):
        from decimal import Decimal
        from unittest.mock import MagicMock
        from api.interfaces.instrument_metadata import InstrumentMetadata
        from src.agent.runtime_debug.models import DebugSuggestion, RiskLevel
        from src.agent.runtime_debug.service import RuntimeDebugService

        rest_manager = MagicMock()
        rest_manager.get_instrument_metadata.return_value = InstrumentMetadata(
            exchange="CRYPTO_DOT_COM",
            symbol="CRO_USD",
            quantity_precision=0,
            price_precision=5,
            min_quantity=Decimal("1"),
            quantity_step=Decimal("1"),
            min_price=Decimal("0.00001"),
            min_notional=Decimal("1.00"),
        )
        svc = RuntimeDebugService(
            database_manager=self.db_manager,
            vcs=self.vcs,
            rest_manager=rest_manager,
        )
        ack_id = uuid4()
        with self.db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresRuntimeIncidentRepository)
            repo.save(
                RuntimeIncident(
                    id=ack_id,
                    fingerprint="fp-sweep-cro",
                    status=IncidentStatus.ACKNOWLEDGED,
                    category=ErrorCategory.EXCHANGE_VALIDATION,
                    severity=Severity.CRITICAL,
                    component="trading.orders.order_manager",
                    operation="execute_order",
                    asset="CRO_USD",
                    exchange="CRYPTO_DOT_COM",
                    first_seen=datetime.now(timezone.utc),
                    last_seen=datetime.now(timezone.utc),
                    occurrence_count=50,
                    suggestion=DebugSuggestion(
                        summary="Generic error",
                        root_cause="Runtime execution failure.",
                        affected_component="trading.orders.order_manager",
                        proposed_change="Review logs",
                        rationale="Generic",
                        risk=RiskLevel.MEDIUM,
                        requires_code_change=True,
                        requires_configuration_change=False,
                    ),
                )
            )
            repo.add_error_event(
                RuntimeErrorEvent(
                    id=uuid4(),
                    incident_id=ack_id,
                    severity=Severity.CRITICAL,
                    component="trading.orders.order_manager",
                    operation="execute_order",
                    error_type="RuntimeError",
                    message="BELOW_MIN_ORDER_SIZE",
                    asset="CRO_USD",
                    exchange="CRYPTO_DOT_COM",
                    exchange_code=415,
                    http_status=500,
                    metadata={"order_quantity": "19", "order_price": "0.039990"},
                    fingerprint="fp-sweep-cro",
                )
            )

        swept = svc.sweep_critical_incidents(cooldown_seconds=3600.0)
        self.assertIn(str(ack_id), swept)
        # Immediate second sweep respects cooldown
        swept_again = svc.sweep_critical_incidents(cooldown_seconds=3600.0)
        self.assertNotIn(str(ack_id), swept_again)

    def test_insufficient_balance_incident_proposes_config_fix_with_min_qty_in_summary(self):
        from decimal import Decimal
        from unittest.mock import MagicMock
        from api.interfaces.account_balance import AccountBalance
        from api.interfaces.instrument_metadata import InstrumentMetadata
        from src.agent.actions.service import AgentActionService, AgentApprovalService
        from src.agent.configuration.configuration_service import ConfigurationService
        from src.agent.runtime_debug.fingerprint import compute_error_fingerprint
        from src.agent.runtime_debug.service import RuntimeDebugService
        from src.retention.manager import RetentionManager

        # Verify distinct fingerprints for DOGE_USD vs CRO_USD
        fp_doge = compute_error_fingerprint(
            RuntimeErrorEvent(
                exchange="CRYPTO_DOT_COM",
                asset="DOGE_USD",
                operation="execute_order",
                exchange_code=306,
                component="trading.orders.order_manager",
                message="INSUFFICIENT_AVAILABLE_BALANCE",
            )
        )
        fp_cro = compute_error_fingerprint(
            RuntimeErrorEvent(
                exchange="CRYPTO_DOT_COM",
                asset="CRO_USD",
                operation="execute_order",
                exchange_code=306,
                component="trading.orders.order_manager",
                message="INSUFFICIENT_AVAILABLE_BALANCE",
            )
        )
        self.assertNotEqual(fp_doge, fp_cro)

        cro_config = """
assets:
  - name: "Cronos"
    base_ticker_symbol: "CRO"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 19.0
    quote_decimals: 5
    quantity_decimals: 0
    candles_timeframe: "MIN1"
    schedule: 1
    enabled: true
    consensus:
      buy: 0.7
      sell: 0.4
"""
        db_manager = make_temp_db_manager()
        vcs = VCSService(db_manager)
        vcs.seed_if_empty(
            TradingConfig.model_validate(yaml.safe_load(cro_config)),
            author="test",
            message="seed cro",
        )
        event_bus = MessageEventBus()
        action_service = AgentActionService(event_bus=event_bus)
        approval_service = AgentApprovalService(
            vcs=vcs,
            configuration_service=ConfigurationService(vcs=vcs),
            action_service=action_service,
            event_bus=event_bus,
        )
        rest_manager = MagicMock()
        rest_manager.get_instrument_metadata.return_value = InstrumentMetadata(
            exchange="CRYPTO_DOT_COM",
            symbol="CRO_USD",
            quantity_precision=0,
            price_precision=5,
            min_quantity=Decimal("1"),
            quantity_step=Decimal("1"),
            min_price=Decimal("0.00001"),
            min_notional=Decimal("1.00"),
        )
        rest_manager.get_account_balance.return_value = [
            AccountBalance(currency="CRO", available_balance=Decimal("0"))
        ]
        rest_manager.get_open_orders.return_value = []

        shared_debug_service = RuntimeDebugService(
            database_manager=db_manager,
            vcs=vcs,
            event_bus=event_bus,
            rest_manager=rest_manager,
            agent_event_bus=event_bus,
            action_service=action_service,
            approval_service=approval_service,
        )
        app = ChatApp.create(
            trading_proxy=make_test_trading_proxy(),
            agent=AgentGateway(FakeLlmAdapter(chunks=["ok"]), vcs=vcs),
            event_bus=event_bus,
            db_manager=db_manager,
            vcs=vcs,
            llm_manager=make_test_llm_manager(db_manager),
            retention_manager=RetentionManager(db_manager),
            runtime_debug_service=shared_debug_service,
        )
        client = TestClient(app)

        inc_id = uuid4()
        with db_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresRuntimeIncidentRepository)
            repo.save(
                RuntimeIncident(
                    id=inc_id,
                    fingerprint=fp_cro,
                    status=IncidentStatus.DETECTED,
                    category=ErrorCategory.EXCHANGE_VALIDATION,
                    severity=Severity.CRITICAL,
                    component="trading.orders.order_manager",
                    operation="execute_order",
                    asset="CRO_USD",
                    exchange="CRYPTO_DOT_COM",
                    first_seen=datetime.now(timezone.utc),
                    last_seen=datetime.now(timezone.utc),
                    occurrence_count=24351,
                )
            )
            repo.add_error_event(
                RuntimeErrorEvent(
                    id=uuid4(),
                    incident_id=inc_id,
                    severity=Severity.CRITICAL,
                    component="trading.orders.order_manager",
                    operation="execute_order",
                    error_type="RuntimeError",
                    message="INSUFFICIENT_AVAILABLE_BALANCE",
                    asset="CRO_USD",
                    exchange="CRYPTO_DOT_COM",
                    exchange_code=306,
                    http_status=500,
                    metadata={"trade_action": "SELL", "order_quantity": "47", "order_price": "0.039970"},
                    fingerprint=fp_cro,
                )
            )

        res = client.post(f"/api/v1/runtime/incidents/{inc_id}/propose-fix")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("exchange min_qty=1", data["diagnosis"]["summary"])
        self.assertIn("exchange min_qty=1", data["suggestion"]["summary"])
        self.assertTrue(data["suggestion"]["requires_configuration_change"])
        self.assertFalse(data["suggestion"]["requires_code_change"])
        self.assertIsNotNone(data["approval_request"])
        changes = data["approval_request"]["proposed_change"]["changes"]
        self.assertEqual(changes[0]["path"], "assets.CRO_USD.enabled")
        self.assertEqual(changes[0]["old_value"], True)
        self.assertEqual(changes[0]["new_value"], False)
