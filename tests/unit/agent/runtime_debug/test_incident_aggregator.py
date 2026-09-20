from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.agent.runtime_debug.fingerprint import compute_error_fingerprint
from src.agent.runtime_debug.incident_aggregator import IncidentAggregator
from src.agent.runtime_debug.models import (
    ErrorCategory,
    ErrorSeverity,
    RuntimeErrorEvent,
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


def test_fingerprint_ignores_dynamic_ids_and_floats():
    msg1 = "Invalid quantity format: 0.000078 for order 28704f16-32ca-4483-a718-533228e4ceac at 2026-09-20T15:00:00Z"
    msg2 = "Invalid quantity format: 0.000123 for order 98765432-1111-2222-3333-444444444444 at 2026-09-20T15:05:00Z"

    event1 = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        operation="execute_order",
        exchange_code=213,
        component="trading.orders.order_manager",
        message=msg1,
    )
    event2 = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        operation="execute_order",
        exchange_code=213,
        component="trading.orders.order_manager",
        message=msg2,
    )

    fp1 = compute_error_fingerprint(event1)
    fp2 = compute_error_fingerprint(event2)

    assert fp1 == fp2


def test_incident_aggregator_deduplicates_burst_errors():
    db_manager = InMemoryDatabaseManager()
    event_bus = MagicMock()
    callback = MagicMock()

    aggregator = IncidentAggregator(
        database_manager=db_manager,
        event_bus=event_bus,
        investigation_callback=callback,
        auto_investigate=True,
    )

    event1 = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        operation="execute_order",
        exchange_code=213,
        component="trading.orders.order_manager",
        message="Invalid quantity format: 0.000078",
        asset="BTC_USD",
    )
    incident1 = aggregator.process_error_event(event1)

    assert incident1.occurrence_count == 1
    assert incident1.category == ErrorCategory.EXCHANGE_VALIDATION
    assert incident1.severity == ErrorSeverity.CRITICAL
    callback.assert_called_once_with(str(incident1.id))

    event2 = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        operation="execute_order",
        exchange_code=213,
        component="trading.orders.order_manager",
        message="Invalid quantity format: 0.000099",
        asset="BTC_USD",
    )
    incident2 = aggregator.process_error_event(event2)

    assert incident2.id == incident1.id
    assert incident2.occurrence_count == 2
    assert callback.call_count == 1  # Not triggered twice for duplicate burst


def test_classify_error_categories():
    rate_limit_ev = RuntimeErrorEvent(http_status=429, message="Too Many Requests")
    cat, sev = IncidentAggregator.classify_error(rate_limit_ev)
    assert cat == ErrorCategory.RATE_LIMIT
    assert sev == ErrorSeverity.WARNING

    auth_ev = RuntimeErrorEvent(http_status=401, message="Unauthorized API key")
    cat, sev = IncidentAggregator.classify_error(auth_ev)
    assert cat == ErrorCategory.AUTHENTICATION
    assert sev == ErrorSeverity.CRITICAL

    network_ev = RuntimeErrorEvent(http_status=503, message="Service Unavailable: timeout")
    cat, sev = IncidentAggregator.classify_error(network_ev)
    assert cat == ErrorCategory.TRANSIENT_NETWORK
    assert sev == ErrorSeverity.WARNING
