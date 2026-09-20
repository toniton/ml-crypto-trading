from unittest.mock import MagicMock
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.agent.runtime_debug.graph import RuntimeDebugGraph
from src.agent.runtime_debug.models import (
    ConfidenceLevel,
    ErrorCategory,
    ErrorSeverity,
    IncidentStatus,
    RiskLevel,
    RuntimeErrorEvent,
    RuntimeIncident,
)
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
            severity=ErrorSeverity.CRITICAL,
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
