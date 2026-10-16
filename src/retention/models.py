from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from src.retention.durations import parse_duration


class DataCategory(str, Enum):
    FINANCIAL = "FINANCIAL"
    TRADING_DECISION = "TRADING_DECISION"
    TRACE = "TRACE"
    METRICS = "METRICS"
    RUNTIME_ALERT = "RUNTIME_ALERT"
    EXPERIMENT = "EXPERIMENT"
    EXPERIMENT_ARTIFACT = "EXPERIMENT_ARTIFACT"
    REPORT = "REPORT"
    CONFIG_HISTORY = "CONFIG_HISTORY"
    MARKET_DATA = "MARKET_DATA"
    MARKET_DATA_BUFFER = "MARKET_DATA_BUFFER"
    APPLICATION_LOG = "APPLICATION_LOG"
    CACHE = "CACHE"


class RetentionMode(str, Enum):
    DELETE = "DELETE"
    ARCHIVE = "ARCHIVE"
    AGGREGATE_THEN_DELETE = "AGGREGATE_THEN_DELETE"
    KEEP = "KEEP"


class RetentionRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class RetentionTrigger(str, Enum):
    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"
    PREVIEW = "PREVIEW"


class RetentionAuditEventType(str, Enum):
    POLICY_UPDATED = "POLICY_UPDATED"
    RUN_STARTED = "RUN_STARTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"
    HOLD_ADDED = "HOLD_ADDED"
    HOLD_RELEASED = "HOLD_RELEASED"


@dataclass
class RetentionPolicy:
    policy_id: str
    data_category: DataCategory
    retention_period: str
    retention_mode: RetentionMode
    scope: str = "GLOBAL"
    enabled: bool = True
    grace_period: str = "0d"
    description: str = ""
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None

    def period_delta(self) -> Optional[timedelta]:
        return parse_duration(self.retention_period)

    def grace_delta(self) -> timedelta:
        return parse_duration(self.grace_period) or timedelta(0)

    def cutoff(self, now: datetime) -> Optional[datetime]:
        period = self.period_delta()
        if period is None:
            return None
        return now - period - self.grace_delta()

    def to_dict(
            self,
            record_count: Optional[int] = None,
            estimated_storage_bytes: Optional[int] = None,
    ) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "data_category": self.data_category.value,
            "retention_period": self.retention_period,
            "retention_mode": self.retention_mode.value,
            "scope": self.scope,
            "enabled": self.enabled,
            "grace_period": self.grace_period,
            "description": self.description,
            "record_count": record_count,
            "estimated_storage_bytes": estimated_storage_bytes,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "updated_by": self.updated_by,
        }


@dataclass
class SkipReason:
    reason: str
    count: int
    detail: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"reason": self.reason, "count": self.count, "detail": self.detail}


@dataclass
class CategoryOutcome:
    data_category: DataCategory
    policy_id: str
    retention_mode: RetentionMode
    examined: int = 0
    eligible: int = 0
    archived: int = 0
    aggregated: int = 0
    deleted: int = 0
    skipped: int = 0
    skipped_reasons: list[SkipReason] = field(default_factory=list)
    storage_bytes: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_category": self.data_category.value,
            "policy_id": self.policy_id,
            "retention_mode": self.retention_mode.value,
            "examined": self.examined,
            "eligible": self.eligible,
            "archived": self.archived,
            "aggregated": self.aggregated,
            "deleted": self.deleted,
            "skipped": self.skipped,
            "skipped_reasons": [reason.to_dict() for reason in self.skipped_reasons],
            "storage_bytes": self.storage_bytes,
        }


@dataclass
class RetentionRun:
    run_id: str = field(default_factory=lambda: str(uuid4()))
    status: RetentionRunStatus = RetentionRunStatus.PENDING
    trigger: RetentionTrigger = RetentionTrigger.SCHEDULED
    dry_run: bool = True
    policy_version: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    categories: list[CategoryOutcome] = field(default_factory=list)
    storage_reclaimed_bytes: Optional[int] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "trigger": self.trigger.value,
            "dry_run": self.dry_run,
            "policy_version": self.policy_version,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "categories": [category.to_dict() for category in self.categories],
            "storage_reclaimed_bytes": self.storage_reclaimed_bytes,
            "error": self.error,
        }


@dataclass
class RetentionAuditEvent:
    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: RetentionAuditEventType = RetentionAuditEventType.POLICY_UPDATED
    policy_id: Optional[str] = None
    actor: Optional[str] = None
    old_value: Optional[dict[str, Any]] = None
    new_value: Optional[dict[str, Any]] = None
    run_id: Optional[str] = None
    detail: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "policy_id": self.policy_id,
            "actor": self.actor,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "run_id": self.run_id,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
