from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.agent.runtime_debug.models import (
    ConfidenceLevel,
    DebugDiagnosis,
    DebugSuggestion,
    ErrorCategory,
    ErrorSeverity,
    IncidentStatus,
    RiskLevel,
    RuntimeErrorEvent,
    RuntimeIncident,
)
from src.database.repositories.providers.postgres_runtime_incident_repository import (
    PostgresRuntimeIncidentRepository,
)
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


def setup_in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def test_save_and_get_incident():
    session = setup_in_memory_db()
    repo = PostgresRuntimeIncidentRepository(database_session=session)

    incident = RuntimeIncident(
        id=uuid4(),
        fingerprint="fp-test-1",
        status=IncidentStatus.DETECTED,
        category=ErrorCategory.EXCHANGE_VALIDATION,
        severity=ErrorSeverity.ERROR,
        component="trading.orders.order_manager",
        asset="BTC_USD",
        exchange="CRYPTO_DOT_COM",
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
        occurrence_count=1,
    )

    repo.save(incident)
    fetched = repo.get(str(incident.id))

    assert fetched is not None
    assert fetched.id == incident.id
    assert fetched.fingerprint == "fp-test-1"
    assert fetched.category == ErrorCategory.EXCHANGE_VALIDATION


def test_get_by_fingerprint_with_status_filter():
    session = setup_in_memory_db()
    repo = PostgresRuntimeIncidentRepository(database_session=session)

    incident = RuntimeIncident(
        id=uuid4(),
        fingerprint="fp-dedupe",
        status=IncidentStatus.DETECTED,
        category=ErrorCategory.EXCHANGE_VALIDATION,
        severity=ErrorSeverity.ERROR,
        component="trading.orders.order_manager",
        asset="BTC_USD",
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    repo.save(incident)

    found = repo.get_by_fingerprint("fp-dedupe", status_filter=[IncidentStatus.DETECTED])
    assert found is not None
    assert found.id == incident.id

    not_found = repo.get_by_fingerprint("fp-dedupe", status_filter=[IncidentStatus.RESOLVED])
    assert not_found is None


def test_add_and_get_error_events():
    session = setup_in_memory_db()
    repo = PostgresRuntimeIncidentRepository(database_session=session)

    incident = RuntimeIncident(
        id=uuid4(),
        fingerprint="fp-events",
        status=IncidentStatus.DETECTED,
        category=ErrorCategory.EXCHANGE_VALIDATION,
        severity=ErrorSeverity.ERROR,
        component="trading.orders.order_manager",
    )
    repo.save(incident)

    event1 = RuntimeErrorEvent(
        id=uuid4(),
        incident_id=incident.id,
        severity=ErrorSeverity.ERROR,
        component="trading.orders.order_manager",
        error_type="RuntimeError",
        message="Invalid quantity format",
        fingerprint="fp-events",
    )
    repo.add_error_event(event1)

    events = repo.get_error_events(incident.id)
    assert len(events) == 1
    assert events[0].id == event1.id
    assert events[0].message == "Invalid quantity format"


def test_update_diagnosis_and_suggestion():
    session = setup_in_memory_db()
    repo = PostgresRuntimeIncidentRepository(database_session=session)

    incident = RuntimeIncident(
        id=uuid4(),
        fingerprint="fp-diag",
        status=IncidentStatus.DETECTED,
        category=ErrorCategory.EXCHANGE_VALIDATION,
        severity=ErrorSeverity.ERROR,
        component="trading.orders.order_manager",
    )
    repo.save(incident)

    diag = DebugDiagnosis(
        summary="Quantity not normalized",
        suspected_component="order_manager",
        suspected_root_cause="precision",
        confidence=ConfidenceLevel.CONFIRMED,
    )
    repo.update_diagnosis(incident.id, diag, ConfidenceLevel.CONFIRMED.value)

    fetched = repo.get(str(incident.id))
    assert fetched.status == IncidentStatus.DIAGNOSED
    assert fetched.diagnosis.summary == "Quantity not normalized"

    sugg = DebugSuggestion(
        summary="Fix lot size",
        root_cause="precision",
        affected_component="order_manager",
        proposed_change="quantize",
        rationale="Crypto.com rules",
        risk=RiskLevel.MEDIUM,
    )
    repo.update_suggestion(incident.id, sugg, IncidentStatus.SUGGESTION_READY)

    fetched_after_sugg = repo.get(str(incident.id))
    assert fetched_after_sugg.status == IncidentStatus.SUGGESTION_READY
    assert fetched_after_sugg.suggestion.summary == "Fix lot size"
