from unittest.mock import MagicMock
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.agent.runtime_debug.graph import RuntimeDebugGraph
from src.agent.runtime_debug.models import (
    ConfidenceLevel,
    ErrorCategory,
    IncidentStatus,
    RiskLevel,
    RuntimeErrorEvent,
    RuntimeIncident,
)
from src.core.severity import Severity
from src.agent.runtime_debug.service import RuntimeDebugService
from src.agent.runtime_debug.tools import RuntimeDebugToolbox
from src.database.repositories.providers.postgres_runtime_incident_repository import (
    PostgresRuntimeIncidentRepository,
)
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.database.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork


class InMemoryDatabaseManager:
    def __init__(self):
        self.engine = create_engine("sqlite:///:memory:")
        SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

    def get_unit_of_work(self):
        return SqlAlchemyUnitOfWork(self.session_factory())


def test_runtime_debug_graph_execution_crypto_dot_com():
    db_manager = InMemoryDatabaseManager()
    toolbox = RuntimeDebugToolbox(database_manager=db_manager)
    graph = RuntimeDebugGraph(toolbox=toolbox).build()

    error_event = RuntimeErrorEvent(
        id=uuid4(),
        exchange="CRYPTO_DOT_COM",
        exchange_code=213,
        message="Invalid quantity format: 0.000078",
        asset="BTC_USD",
        metadata={"order_quantity": "0.000078"},
    )

    state = {
        "error_event": error_event,
    }
    result = graph.invoke(state)

    assert result.get("diagnosis") is not None
    diagnosis = result["diagnosis"]
    assert diagnosis.confidence == ConfidenceLevel.CONFIRMED
    assert len(diagnosis.evidence) > 0

    assert result.get("suggestion") is not None
    suggestion = result["suggestion"]
    assert suggestion.requires_code_change is True
    assert suggestion.risk == RiskLevel.HIGH
    assert "quantity" in suggestion.proposed_change.lower()

    assert result.get("presentation") is not None


def test_runtime_debug_service_investigate_and_update():
    db_manager = InMemoryDatabaseManager()
    event_bus = MagicMock()
    service = RuntimeDebugService(database_manager=db_manager, event_bus=event_bus)

    incident_id = uuid4()
    with db_manager.get_unit_of_work() as uow:
        repo = uow.get_repository(PostgresRuntimeIncidentRepository)
        incident = RuntimeIncident(
            id=incident_id,
            fingerprint="fp-test-service",
            status=IncidentStatus.DETECTED,
            category=ErrorCategory.EXCHANGE_VALIDATION,
            severity=Severity.CRITICAL,
            component="trading.orders.order_manager",
            asset="BTC_USD",
            exchange="CRYPTO_DOT_COM",
        )
        repo.save(incident)

        event = RuntimeErrorEvent(
            id=uuid4(),
            incident_id=incident_id,
            exchange="CRYPTO_DOT_COM",
            exchange_code=213,
            message="Invalid quantity format",
            asset="BTC_USD",
            metadata={"order_quantity": "0.000078"},
            fingerprint="fp-test-service",
        )
        repo.add_error_event(event)

    result = service.investigate_incident(str(incident_id))

    assert result.get("diagnosis") is not None
    assert result.get("suggestion") is not None
    event_bus.publish.assert_called_once()

    updated_incident = service.get_incident(str(incident_id))
    assert updated_incident.status == IncidentStatus.SUGGESTION_READY
    assert updated_incident.diagnosis is not None
    assert updated_incident.suggestion is not None


def test_runtime_debug_service_below_min_order_size_emits_message_and_approval():
    from decimal import Decimal
    from api.interfaces.instrument_metadata import InstrumentMetadata
    from src.agent.actions.service import AgentActionService, AgentApprovalService
    from src.core.interfaces.conversation_store import RESERVED_AGENT_SESSION_ID
    from src.events.agent_events import AgentApprovalRequestedEvent, AgentMessageCreatedEvent

    db_manager = InMemoryDatabaseManager()
    trading_event_bus = MagicMock()
    agent_event_bus = MagicMock()
    rest_manager = MagicMock()
    rest_manager.get_instrument_metadata.return_value = InstrumentMetadata(
        exchange="CRYPTO_DOT_COM",
        symbol="CRO_USD",
        quantity_precision=0,
        price_precision=5,
        min_quantity=Decimal("25"),
        quantity_step=Decimal("1"),
        min_price=Decimal("0.00001"),
        min_notional=Decimal("1.00"),
    )
    vcs = MagicMock()
    vcs.head.return_value = MagicMock(hash="abc12345def")
    vcs.checkout.return_value = {"assets": {"CRO_USD": {"min_quantity": 10}}}
    config_service = MagicMock()
    llm = MagicMock()
    llm.generate.return_value = "CRO_USD order quantity 19 is below Crypto.com minimum size of 25."

    action_service = AgentActionService(event_bus=agent_event_bus)
    approval_service = AgentApprovalService(
        vcs=vcs,
        configuration_service=config_service,
        action_service=action_service,
        event_bus=agent_event_bus,
    )
    service = RuntimeDebugService(
        database_manager=db_manager,
        vcs=vcs,
        llm=llm,
        event_bus=trading_event_bus,
        rest_manager=rest_manager,
        agent_event_bus=agent_event_bus,
        action_service=action_service,
        approval_service=approval_service,
    )

    incident_id = uuid4()
    with db_manager.get_unit_of_work() as uow:
        repo = uow.get_repository(PostgresRuntimeIncidentRepository)
        repo.save(
            RuntimeIncident(
                id=incident_id,
                fingerprint="fp-cro-min-size",
                status=IncidentStatus.DETECTED,
                category=ErrorCategory.EXCHANGE_VALIDATION,
                severity=Severity.CRITICAL,
                component="trading.orders.order_manager",
                operation="execute_order",
                asset="CRO_USD",
                exchange="CRYPTO_DOT_COM",
            )
        )
        repo.add_error_event(
            RuntimeErrorEvent(
                id=uuid4(),
                incident_id=incident_id,
                exchange="CRYPTO_DOT_COM",
                exchange_code=415,
                http_status=500,
                operation="execute_order",
                message="BELOW_MIN_ORDER_SIZE",
                asset="CRO_USD",
                metadata={"order_quantity": "19", "order_price": "0.040180"},
                fingerprint="fp-cro-min-size",
            )
        )

    result = service.investigate_incident(str(incident_id))

    suggestion = result["suggestion"]
    assert suggestion.requires_configuration_change is True
    assert suggestion.requires_code_change is False
    assert suggestion.affected_component == "assets.CRO_USD.min_quantity"
    assert "25" in suggestion.proposed_change

    published_events = [call.args[0] for call in agent_event_bus.publish.call_args_list]
    msg_events = [e for e in published_events if isinstance(e, AgentMessageCreatedEvent)]
    approval_events = [e for e in published_events if isinstance(e, AgentApprovalRequestedEvent)]
    assert len(msg_events) == 1
    assert msg_events[0].conversation_id == RESERVED_AGENT_SESSION_ID
    assert len(approval_events) == 1
    assert approval_events[0].approval_payload["conversation_id"] == RESERVED_AGENT_SESSION_ID
    changes = approval_events[0].approval_payload["proposed_change"]["changes"]
    assert changes[0]["path"] == "assets.CRO_USD.min_quantity"
    assert changes[0]["old_value"] == 10
    assert changes[0]["new_value"] == 25.0
