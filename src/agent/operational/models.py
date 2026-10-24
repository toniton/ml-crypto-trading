from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional, Sequence


class OperationalReadinessStatus(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    PAUSED = "paused"
    HALTED = "halted"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OperationalConditionSummary:
    condition: str
    scope_type: str
    scope_identifier: str
    severity: str
    first_detected_at: datetime
    last_observed_at: datetime


@dataclass(frozen=True)
class OperationalContext:
    status: OperationalReadinessStatus
    health_state: str
    is_trading_allowed: bool
    active_conditions: Sequence[OperationalConditionSummary]
    effective_permissions: Sequence[str]
    observed_at: datetime
    snapshot_version: int
    is_available: bool
    collection_errors: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def unavailable(cls, error_reason: str = "Health monitor not configured") -> OperationalContext:
        return cls(
            status=OperationalReadinessStatus.UNKNOWN,
            health_state="UNKNOWN",
            is_trading_allowed=False,
            active_conditions=(),
            effective_permissions=(),
            observed_at=datetime.now(timezone.utc),
            snapshot_version=0,
            is_available=False,
            collection_errors=(error_reason,),
        )

    def is_stale(self, max_age_seconds: float = 60.0, now: Optional[datetime] = None) -> bool:
        current_time = now or datetime.now(timezone.utc)
        return (current_time - self.observed_at).total_seconds() > max_age_seconds
