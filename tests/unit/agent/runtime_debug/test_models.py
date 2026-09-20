from datetime import datetime, timezone
from uuid import uuid4

from src.agent.runtime_debug.models import (
    ConfidenceLevel,
    DebugDiagnosis,
    DebugSuggestion,
    ErrorCategory,
    ErrorSeverity,
    Evidence,
    IncidentStatus,
    RiskLevel,
    RuntimeErrorEvent,
    RuntimeIncident,
)


def test_evidence_serialization():
    evidence = Evidence(
        title="Invalid quantity format",
        description="Exchange returned error 213",
        source="exchange_response",
        data={"code": 213, "quantity": "0.000078"},
    )
    serialized = evidence.to_dict()
    restored = Evidence.from_dict(serialized)

    assert restored.title == "Invalid quantity format"
    assert restored.source == "exchange_response"
    assert restored.data["code"] == 213


def test_debug_diagnosis_serialization():
    diagnosis = DebugDiagnosis(
        summary="Quantity precision mismatch on Crypto.com",
        suspected_component="trading.orders.order_manager",
        suspected_root_cause="quantity_normalization",
        evidence=[
            Evidence(
                title="Error 213",
                description="Invalid quantity format",
                source="exchange",
            )
        ],
        confidence=ConfidenceLevel.CONFIRMED,
    )
    serialized = diagnosis.to_dict()
    restored = DebugDiagnosis.from_dict(serialized)

    assert restored.summary == diagnosis.summary
    assert restored.confidence == ConfidenceLevel.CONFIRMED
    assert len(restored.evidence) == 1
    assert restored.evidence[0].title == "Error 213"


def test_debug_suggestion_serialization():
    suggestion = DebugSuggestion(
        summary="Normalize order quantity against BTC_USD step size",
        root_cause="Order quantity exceeds allowed decimal precision",
        affected_component="quantity_calculator",
        proposed_change="Apply quantize() with instrument precision",
        rationale="Crypto.com rejects non-normalized lot sizes",
        evidence=[],
        risk=RiskLevel.HIGH,
        requires_code_change=True,
        requires_configuration_change=False,
    )
    serialized = suggestion.to_dict()
    restored = DebugSuggestion.from_dict(serialized)

    assert restored.summary == suggestion.summary
    assert restored.requires_code_change is True
    assert restored.risk == RiskLevel.HIGH


def test_runtime_error_event_serialization():
    event_id = uuid4()
    event = RuntimeErrorEvent(
        id=event_id,
        timestamp=datetime(2026, 9, 20, 15, 0, 0, tzinfo=timezone.utc),
        severity=ErrorSeverity.CRITICAL,
        component="trading.orders.order_manager",
        error_type="RuntimeError",
        message="Invalid quantity format",
        traceback="traceback...",
        operation="execute_order",
        asset="BTC_USD",
        order_id="order-123",
        exchange="CRYPTO_DOT_COM",
        exchange_code=213,
        http_status=400,
        commit_hash="7bf9eea36412d9d8049154dc39f51e900859537629abd9a1c2ea281d771065c0",
        fingerprint="test-fingerprint-sha",
    )
    serialized = event.to_dict()
    restored = RuntimeErrorEvent.from_dict(serialized)

    assert restored.id == event_id
    assert restored.exchange_code == 213
    assert restored.http_status == 400
    assert restored.severity == ErrorSeverity.CRITICAL
    assert restored.fingerprint == "test-fingerprint-sha"


def test_runtime_incident_serialization():
    incident_id = uuid4()
    incident = RuntimeIncident(
        id=incident_id,
        fingerprint="fp-123",
        status=IncidentStatus.DETECTED,
        category=ErrorCategory.EXCHANGE_VALIDATION,
        severity=ErrorSeverity.ERROR,
        component="trading.orders.order_manager",
        operation="execute_order",
        asset="BTC_USD",
        exchange="CRYPTO_DOT_COM",
        commit_hash="abc1234",
        first_seen=datetime(2026, 9, 20, 15, 0, 0, tzinfo=timezone.utc),
        last_seen=datetime(2026, 9, 20, 15, 5, 0, tzinfo=timezone.utc),
        occurrence_count=5,
        error_events=[uuid4(), uuid4()],
    )
    serialized = incident.to_dict()
    restored = RuntimeIncident.from_dict(serialized)

    assert restored.id == incident_id
    assert restored.occurrence_count == 5
    assert len(restored.error_events) == 2
    assert restored.category == ErrorCategory.EXCHANGE_VALIDATION
