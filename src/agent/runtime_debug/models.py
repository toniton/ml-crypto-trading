from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4


class ErrorSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ErrorCategory(str, Enum):
    EXCHANGE_VALIDATION = "EXCHANGE_VALIDATION"
    TRANSIENT_NETWORK = "TRANSIENT_NETWORK"
    AUTHENTICATION = "AUTHENTICATION"
    RATE_LIMIT = "RATE_LIMIT"
    CONFIGURATION = "CONFIGURATION"
    DATA = "DATA"
    DATABASE = "DATABASE"
    APPLICATION = "APPLICATION"
    UNKNOWN = "UNKNOWN"


class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    DIAGNOSED = "DIAGNOSED"
    SUGGESTION_READY = "SUGGESTION_READY"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"


class ConfidenceLevel(str, Enum):
    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    POSSIBLE = "POSSIBLE"
    UNKNOWN = "UNKNOWN"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Evidence:
    title: str
    description: str
    source: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
        return cls(
            title=data.get("title", ""),
            description=data.get("description", ""),
            source=data.get("source", ""),
            data=data.get("data") or {},
        )


@dataclass(frozen=True)
class DebugDiagnosis:
    summary: str
    suspected_component: str
    suspected_root_cause: str
    evidence: list[Evidence] = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.LIKELY

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "suspected_component": self.suspected_component,
            "suspected_root_cause": self.suspected_root_cause,
            "evidence": [e.to_dict() for e in self.evidence],
            "confidence": self.confidence.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DebugDiagnosis:
        return cls(
            summary=data.get("summary", ""),
            suspected_component=data.get("suspected_component", ""),
            suspected_root_cause=data.get("suspected_root_cause", ""),
            evidence=[Evidence.from_dict(e) for e in data.get("evidence", [])],
            confidence=ConfidenceLevel(data.get("confidence", ConfidenceLevel.LIKELY.value)),
        )


@dataclass(frozen=True)
class DebugSuggestion:
    summary: str
    root_cause: str
    affected_component: str
    proposed_change: str
    rationale: str
    evidence: list[Evidence] = field(default_factory=list)
    risk: RiskLevel = RiskLevel.HIGH
    requires_code_change: bool = False
    requires_configuration_change: bool = False
    requires_restart: bool = False
    requires_manual_validation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "root_cause": self.root_cause,
            "affected_component": self.affected_component,
            "proposed_change": self.proposed_change,
            "rationale": self.rationale,
            "evidence": [e.to_dict() for e in self.evidence],
            "risk": self.risk.value,
            "requires_code_change": self.requires_code_change,
            "requires_configuration_change": self.requires_configuration_change,
            "requires_restart": self.requires_restart,
            "requires_manual_validation": self.requires_manual_validation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DebugSuggestion:
        return cls(
            summary=data.get("summary", ""),
            root_cause=data.get("root_cause", ""),
            affected_component=data.get("affected_component", ""),
            proposed_change=data.get("proposed_change", ""),
            rationale=data.get("rationale", ""),
            evidence=[Evidence.from_dict(e) for e in data.get("evidence", [])],
            risk=RiskLevel(data.get("risk", RiskLevel.HIGH.value)),
            requires_code_change=data.get("requires_code_change", False),
            requires_configuration_change=data.get("requires_configuration_change", False),
            requires_restart=data.get("requires_restart", False),
            requires_manual_validation=data.get("requires_manual_validation", True),
        )


@dataclass
class RuntimeErrorEvent:
    id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    severity: ErrorSeverity = ErrorSeverity.ERROR
    component: str = ""
    error_type: str = ""
    message: str = ""
    traceback: Optional[str] = None
    operation: Optional[str] = None
    asset: Optional[str] = None
    order_id: Optional[str] = None
    exchange: Optional[str] = None
    exchange_code: Optional[int] = None
    http_status: Optional[int] = None
    commit_hash: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""
    incident_id: Optional[UUID] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "component": self.component,
            "error_type": self.error_type,
            "message": self.message,
            "traceback": self.traceback,
            "operation": self.operation,
            "asset": self.asset,
            "order_id": self.order_id,
            "exchange": self.exchange,
            "exchange_code": self.exchange_code,
            "http_status": self.http_status,
            "commit_hash": self.commit_hash,
            "metadata": self.metadata,
            "fingerprint": self.fingerprint,
            "incident_id": str(self.incident_id) if self.incident_id else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeErrorEvent:
        raw_ts = data.get("timestamp")
        if isinstance(raw_ts, str):
            ts = datetime.fromisoformat(raw_ts)
        elif isinstance(raw_ts, datetime):
            ts = raw_ts
        else:
            ts = datetime.now(timezone.utc)

        raw_id = data.get("id")
        event_id = UUID(raw_id) if isinstance(raw_id, str) else (raw_id or uuid4())

        raw_inc_id = data.get("incident_id")
        incident_id = UUID(raw_inc_id) if isinstance(raw_inc_id, str) and raw_inc_id else raw_inc_id

        return cls(
            id=event_id,
            timestamp=ts,
            severity=ErrorSeverity(data.get("severity", ErrorSeverity.ERROR.value)),
            component=data.get("component", ""),
            error_type=data.get("error_type", ""),
            message=data.get("message", ""),
            traceback=data.get("traceback"),
            operation=data.get("operation"),
            asset=data.get("asset"),
            order_id=data.get("order_id"),
            exchange=data.get("exchange"),
            exchange_code=data.get("exchange_code"),
            http_status=data.get("http_status"),
            commit_hash=data.get("commit_hash"),
            metadata=data.get("metadata") or {},
            fingerprint=data.get("fingerprint", ""),
            incident_id=incident_id,
        )


@dataclass
class RuntimeIncident:
    id: UUID = field(default_factory=uuid4)
    fingerprint: str = ""
    status: IncidentStatus = IncidentStatus.DETECTED
    category: ErrorCategory = ErrorCategory.UNKNOWN
    severity: ErrorSeverity = ErrorSeverity.ERROR
    component: str = ""
    operation: Optional[str] = None
    asset: Optional[str] = None
    exchange: Optional[str] = None
    commit_hash: Optional[str] = None
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    occurrence_count: int = 1
    error_events: list[UUID] = field(default_factory=list)
    diagnosis: Optional[DebugDiagnosis] = None
    suggestion: Optional[DebugSuggestion] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "fingerprint": self.fingerprint,
            "status": self.status.value,
            "category": self.category.value,
            "severity": self.severity.value,
            "component": self.component,
            "operation": self.operation,
            "asset": self.asset,
            "exchange": self.exchange,
            "commit_hash": self.commit_hash,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "occurrence_count": self.occurrence_count,
            "error_events": [str(e) for e in self.error_events],
            "diagnosis": self.diagnosis.to_dict() if self.diagnosis else None,
            "suggestion": self.suggestion.to_dict() if self.suggestion else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeIncident:
        raw_id = data.get("id")
        incident_id = UUID(raw_id) if isinstance(raw_id, str) else (raw_id or uuid4())

        def parse_dt(val: Any) -> datetime:
            if isinstance(val, str):
                return datetime.fromisoformat(val)
            if isinstance(val, datetime):
                return val
            return datetime.now(timezone.utc)

        diag_raw = data.get("diagnosis")
        diag = DebugDiagnosis.from_dict(diag_raw) if diag_raw else None

        sugg_raw = data.get("suggestion")
        sugg = DebugSuggestion.from_dict(sugg_raw) if sugg_raw else None

        raw_events = data.get("error_events") or []
        event_ids = [UUID(e) if isinstance(e, str) else e for e in raw_events]

        return cls(
            id=incident_id,
            fingerprint=data.get("fingerprint", ""),
            status=IncidentStatus(data.get("status", IncidentStatus.DETECTED.value)),
            category=ErrorCategory(data.get("category", ErrorCategory.UNKNOWN.value)),
            severity=ErrorSeverity(data.get("severity", ErrorSeverity.ERROR.value)),
            component=data.get("component", ""),
            operation=data.get("operation"),
            asset=data.get("asset"),
            exchange=data.get("exchange"),
            commit_hash=data.get("commit_hash"),
            first_seen=parse_dt(data.get("first_seen")),
            last_seen=parse_dt(data.get("last_seen")),
            occurrence_count=data.get("occurrence_count", 1),
            error_events=event_ids,
            diagnosis=diag,
            suggestion=sugg,
            notes=data.get("notes"),
        )
